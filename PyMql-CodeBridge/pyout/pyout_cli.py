#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mini‑CLI do PyOut.
Comandos: serve | start | stop | status | ping | ensure
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _state_dir() -> Path:
    base = os.environ.get("PYOUT_HOME") or os.environ.get("CMDMT_HOME")
    if base:
        p = Path(base)
    else:
        p = Path.home() / ".cmdmt"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _pid_path() -> Path:
    return _state_dir() / "pyout.pid"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _pyout_server_path() -> Path:
    return BASE_DIR / "pyout_server.py"


def _run_server(host: str, port: int, workers: int) -> int:
    os.environ["PYBRIDGE_MODE"] = "server"
    os.environ["PYBRIDGE_HOST"] = host
    os.environ["PYBRIDGE_PORT"] = str(port)
    if workers > 0:
        os.environ["PYOUT_WORKERS"] = str(workers)
    if "PYOUT_LOG" not in os.environ:
        os.environ["PYOUT_LOG"] = "1"
    import pyout_server

    pyout_server.main()
    return 0


def start(host: str, port: int, workers: int) -> int:
    pid_path = _pid_path()
    if pid_path.exists():
        try:
            pid = int(pid_path.read_text().strip())
            if _pid_alive(pid):
                print(f"pyout já está rodando (pid={pid})")
                return 0
        except Exception:
            pass
        try:
            pid_path.unlink()
        except Exception:
            pass

    env = os.environ.copy()
    env["PYBRIDGE_MODE"] = "server"
    env["PYBRIDGE_HOST"] = host
    env["PYBRIDGE_PORT"] = str(port)
    env.setdefault("PYOUT_LOG", "1")
    if workers > 0:
        env["PYOUT_WORKERS"] = str(workers)

    log_dir = BASE_DIR.parent.parent / "run_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"pyout_{ts}.log"
    with open(log_path, "a", encoding="utf-8") as f:
        try:
            proc = subprocess.Popen(
                [sys.executable, str(_pyout_server_path())],
                stdout=f,
                stderr=f,
                start_new_session=True,
                env=env,
            )
            pid_path.write_text(str(proc.pid))
            print(f"pyout iniciado (pid={proc.pid})")
            return 0
        except Exception as e:
            print(f"falha ao iniciar pyout: {e}")
            return 1


def stop() -> int:
    pid_path = _pid_path()
    if not pid_path.exists():
        print("pyout não está rodando (pidfile ausente)")
        return 1
    try:
        pid = int(pid_path.read_text().strip())
    except Exception:
        print("pidfile inválido")
        return 1
    if not _pid_alive(pid):
        print("pyout já não está rodando")
        try:
            pid_path.unlink()
        except Exception:
            pass
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(0.3)
        if _pid_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass
        try:
            pid_path.unlink()
        except Exception:
            pass
        print("pyout parado")
        return 0
    except Exception as e:
        print(f"falha ao parar pyout: {e}")
        return 1


def status() -> int:
    pid_path = _pid_path()
    if not pid_path.exists():
        print("pyout: parado")
        return 1
    try:
        pid = int(pid_path.read_text().strip())
        if _pid_alive(pid):
            print(f"pyout: rodando (pid={pid})")
            return 0
        print("pyout: parado (pidfile antigo)")
        return 1
    except Exception:
        print("pyout: estado desconhecido")
        return 1


def _parse_hosts(hosts: str) -> list[str]:
    return [h.strip() for h in hosts.replace(";", ",").split(",") if h.strip()]


def _recv_line(sock: socket.socket, timeout: float = 2.0) -> str:
    sock.settimeout(timeout)
    data = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
        if b"\n" in data:
            break
    if b"\n" in data:
        data = data.split(b"\n", 1)[0]
    return data.decode("utf-8", "replace")


def ping(hosts: str, port: int, timeout: float = 2.0) -> tuple[bool, str]:
    last_err = ""
    for h in _parse_hosts(hosts):
        try:
            with socket.create_connection((h, port), timeout=timeout) as s:
                s.sendall((json.dumps({"cmd": "ping"}) + "\n").encode("utf-8"))
                resp = _recv_line(s, timeout=timeout)
                return True, resp.strip()
        except Exception as e:
            last_err = str(e)
    return False, last_err or "ping_failed"


def ensure(hosts: str, port: int) -> int:
    ok, info = ping(hosts, port)
    if ok:
        print("OK pyout_alive")
        return 0
    start("0.0.0.0", port)
    ok2, info2 = ping(hosts, port)
    print(("OK " if ok2 else "ERROR ") + (info2 or "pyout"))
    return 0 if ok2 else 1


def main() -> int:
    parser = argparse.ArgumentParser(prog="pyout")
    sub = parser.add_subparsers(dest="cmd")

    p_serve = sub.add_parser("serve")
    p_serve.add_argument("--host", default=os.environ.get("PYOUT_BIND", "0.0.0.0"))
    p_serve.add_argument("--port", type=int, default=int(os.environ.get("PYOUT_PORT", "9100")))
    p_serve.add_argument("--workers", type=int, default=int(os.environ.get("PYOUT_WORKERS", "2")))

    p_start = sub.add_parser("start")
    p_start.add_argument("--host", default=os.environ.get("PYOUT_BIND", "0.0.0.0"))
    p_start.add_argument("--port", type=int, default=int(os.environ.get("PYOUT_PORT", "9100")))
    p_start.add_argument("--workers", type=int, default=int(os.environ.get("PYOUT_WORKERS", "2")))

    sub.add_parser("stop")
    sub.add_parser("status")

    p_ping = sub.add_parser("ping")
    p_ping.add_argument("--host", default=os.environ.get("PYOUT_HOSTS", "host.docker.internal,127.0.0.1"))
    p_ping.add_argument("--port", type=int, default=int(os.environ.get("PYOUT_PORT", "9100")))

    p_ensure = sub.add_parser("ensure")
    p_ensure.add_argument("--host", default=os.environ.get("PYOUT_HOSTS", "host.docker.internal,127.0.0.1"))
    p_ensure.add_argument("--port", type=int, default=int(os.environ.get("PYOUT_PORT", "9100")))

    args = parser.parse_args()
    cmd = (args.cmd or "").lower()

    if cmd == "serve":
        return _run_server(args.host, args.port, args.workers)
    if cmd == "start":
        return start(args.host, args.port, args.workers)
    if cmd == "stop":
        return stop()
    if cmd == "status":
        return status()
    if cmd == "ping":
        ok, info = ping(args.host, args.port)
        print(("OK " if ok else "ERROR ") + info)
        return 0 if ok else 1
    if cmd == "ensure":
        return ensure(args.host, args.port)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
