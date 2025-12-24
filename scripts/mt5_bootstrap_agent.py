#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bootstrap agent (host side):
- observa MQL5/Files/bootstrap_request.txt
- compila serviços (via cmdmt compile all) quando solicitado
- inicia serviços via mt5_start_service.sh
- escreve bootstrap_response.txt
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


REQ_FILE = "bootstrap_request.txt"
RESP_FILE = "bootstrap_response.txt"


def maybe_wslpath(p: str) -> str:
    p = p.strip().strip('"').strip("'")
    if not p:
        return p
    if p.startswith("/"):
        return p
    if ":" in p and ("\\" in p or p[1:3] == ":\\" or p[1:3] == ":/"):
        try:
            out = subprocess.check_output(["wslpath", "-u", p], stderr=subprocess.DEVNULL)
            return out.decode("utf-8", errors="replace").strip()
        except Exception:
            return p
    return p


def find_terminal_data_dir() -> Path | None:
    env = os.environ.get("CMDMT_MT5_DATA") or os.environ.get("MT5_DATA_DIR")
    if env:
        p = Path(maybe_wslpath(env))
        if p.exists():
            return p
    candidates: list[Path] = []
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal"
        for svc in base.glob("*/MQL5/Services/OficialTelnetServiceSocket.*"):
            candidates.append(svc)
    else:
        base = Path("/mnt/c/Users")
        for svc in base.glob("*/AppData/Roaming/MetaQuotes/Terminal/*/MQL5/Services/OficialTelnetServiceSocket.*"):
            candidates.append(svc)
    if not candidates:
        return None
    svc = max(candidates, key=lambda p: p.stat().st_mtime)
    return svc.parents[2]


def parse_request(text: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip()
    return data


def parse_services(s: str) -> list[str]:
    if not s:
        return []
    parts = []
    for chunk in s.replace(",", ";").split(";"):
        name = chunk.strip()
        if name:
            parts.append(name)
    return parts


def run_cmd(cmd: list[str], timeout: int, env: dict[str, str] | None = None) -> tuple[int, str]:
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            env=env,
        )
        return p.returncode, p.stdout.strip()
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except Exception as e:
        return 1, f"error: {e}"


def write_response(resp_path: Path, lines: list[str]) -> None:
    resp_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def process_once(req_path: Path, resp_path: Path, repo_root: Path, timeout: int, verbose: bool) -> bool:
    if not req_path.exists():
        return False

    text = req_path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        try:
            req_path.unlink()
        except Exception:
            pass
        return False

    data = parse_request(text)
    compile_req = data.get("compile", "0").strip() == "1"
    services = parse_services(data.get("services", ""))
    if not services:
        services = ["OficialTelnetServiceSocket", "PyInService"]

    window_title = data.get("window_title") or os.environ.get("CMDMT_MT5_WINDOW") or "MetaTrader 5"
    start_key = data.get("start_key") or os.environ.get("CMDMT_MT5_START_KEY") or "i"

    resp_lines: list[str] = [
        f"time={time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"compile_requested={1 if compile_req else 0}",
    ]
    ok = True

    if compile_req:
        cmdmt = repo_root / "python" / "cmdmt.py"
        rc, out = run_cmd([sys.executable, str(cmdmt), "compile", "all"], timeout=timeout)
        resp_lines.append(f"compile_rc={rc}")
        if out:
            resp_lines.append("compile_out=" + out.replace("\n", " | "))
        if rc != 0:
            ok = False

    start_script = repo_root / "scripts" / "mt5_start_service.sh"
    for svc in services:
        env = os.environ.copy()
        env["WINDOW_TITLE"] = window_title
        env["START_KEY"] = start_key
        rc, out = run_cmd([str(start_script), svc], timeout=timeout, env=env)
        resp_lines.append(f"start_{svc}={'ok' if rc == 0 else 'fail'}")
        if out:
            resp_lines.append(f"start_{svc}_out=" + out.replace("\n", " | "))
        if rc != 0:
            ok = False

    resp_lines.insert(0, f"ok={1 if ok else 0}")
    write_response(resp_path, resp_lines)

    try:
        req_path.unlink()
    except Exception:
        pass
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Bootstrap agent para serviços MT5")
    ap.add_argument("--data-dir", help="Data directory do MT5 (Terminal/XXXX)")
    ap.add_argument("--poll", type=float, default=0.5, help="intervalo de polling (s)")
    ap.add_argument("--timeout", type=int, default=60, help="timeout por comando (s)")
    ap.add_argument("--once", action="store_true", help="processa um request e sai")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    data_dir = Path(maybe_wslpath(args.data_dir)) if args.data_dir else find_terminal_data_dir()
    if not data_dir or not data_dir.exists():
        print("ERRO: data dir do MT5 nao encontrado. Defina CMDMT_MT5_DATA ou --data-dir.")
        return 2

    files_dir = data_dir / "MQL5" / "Files"
    files_dir.mkdir(parents=True, exist_ok=True)
    req_path = files_dir / REQ_FILE
    resp_path = files_dir / RESP_FILE

    if args.once:
        processed = process_once(req_path, resp_path, repo_root, args.timeout, args.verbose)
        return 0 if processed else 1

    if args.verbose:
        print(f"[bootstrap] watching {req_path}")
    while True:
        processed = process_once(req_path, resp_path, repo_root, args.timeout, args.verbose)
        if processed and args.verbose:
            print("[bootstrap] request processed")
        time.sleep(args.poll)


if __name__ == "__main__":
    raise SystemExit(main())
