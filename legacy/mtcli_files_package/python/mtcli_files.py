#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mtcli_files.py - CLI interativo (tipo telnet) para falar com o MT5 via arquivos cmd_*.txt / resp_*.txt.

Requisitos:
- Rodar o EA "CommandListener.mq5" no MT5 (anexado em qualquer gráfico).
- Pegar o caminho do diretório "MQL5\Files" que o EA imprime no log e passar aqui via --dir.

Exemplo:
  python3 mtcli_files.py --dir "C:\Users\...\MetaQuotes\Terminal\...\MQL5\Files"
  # ou em WSL:
  python3 mtcli_files.py --dir "/mnt/c/Users/.../MetaQuotes/Terminal/.../MQL5/Files"

Comandos:
  help
  ping
  open EURUSD H1
  charts
  buy EURUSD 0.01 [sl] [tp]
  sell EURUSD 0.01 [sl] [tp]
  closeall
  positions
  quit
"""

import argparse
import os
import random
import sys
import time
from pathlib import Path
import subprocess

BLUE_BG = "\033[44m"
WHITE   = "\033[97m"
RESET   = "\033[0m"


def set_blue():
    sys.stdout.write(BLUE_BG + WHITE)
    sys.stdout.flush()


def reset_color():
    sys.stdout.write(RESET)
    sys.stdout.flush()


def maybe_wslpath(p: str) -> str:
    """
    Se você está rodando no WSL e passar um caminho Windows (C:\...), converte para /mnt/c/...
    """
    p = p.strip().strip('"').strip("'")
    if not p:
        return p

    # já parece um caminho linux
    if p.startswith("/"):
        return p

    # heurística de caminho Windows
    if ":" in p and ("\\" in p or p[1:3] == ":\\" or p[1:3] == ":/"):
        try:
            out = subprocess.check_output(["wslpath", "-u", p], stderr=subprocess.DEVNULL)
            return out.decode("utf-8", errors="replace").strip()
        except Exception:
            return p

    return p


def gen_id() -> str:
    return f"{int(time.time()*1000)}_{random.randint(1000,9999)}"


def write_cmd(files_dir: Path, cmd_id: str, cmd_type: str, params: list[str]) -> Path:
    files_dir.mkdir(parents=True, exist_ok=True)
    fname = files_dir / f"cmd_{cmd_id}.txt"
    line = "|".join([cmd_id, cmd_type] + params)

    # IMPORTANTE: evite espaços; o EA lê com FileReadString
    with open(fname, "w", encoding="ascii", errors="ignore", newline="\n") as f:
        f.write(line + "\n")
    return fname


def wait_resp(files_dir: Path, cmd_id: str, timeout: float = 6.0) -> tuple[bool, str, list[str]]:
    resp = files_dir / f"resp_{cmd_id}.txt"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if resp.exists():
            break
        time.sleep(0.05)

    if not resp.exists():
        return False, "timeout esperando resp_*.txt", []

    # Formato:
    # linha1: OK|ERROR
    # linha2: mensagem
    # linhas seguintes: data
    try:
        txt = resp.read_text(encoding="utf-8", errors="replace").splitlines()
    finally:
        # opcional: apaga o resp pra não acumular lixo
        try:
            resp.unlink()
        except Exception:
            pass

    if not txt:
        return False, "resp vazio", []

    status = txt[0].strip().upper()
    msg = txt[1].strip() if len(txt) >= 2 else ""
    data = [ln.rstrip("\r\n") for ln in txt[2:]] if len(txt) >= 3 else []

    return status == "OK", msg, data


def parse_user_line(line: str) -> tuple[str, list[str]] | None:
    parts = line.strip().split()
    if not parts:
        return None

    cmd = parts[0].lower()

    if cmd == "help":
        print(
            "\nComandos:\n"
            "  ping\n"
            "  open SYMBOL TF               (ex: open BTCUSD H1)\n"
            "  charts                       (lista charts abertos)\n"
            "  buy SYMBOL LOTS [sl] [tp]    (sl/tp são preços, opcional)\n"
            "  sell SYMBOL LOTS [sl] [tp]\n"
            "  closeall                     (fecha todas posições)\n"
            "  positions                    (lista posições)\n"
            "  quit\n"
        )
        return None

    if cmd == "ping":
        return "PING", []

    if cmd == "open":
        if len(parts) < 3:
            print("uso: open SYMBOL TF")
            return None
        return "OPEN_CHART", [parts[1], parts[2]]

    if cmd == "charts":
        return "LIST_CHARTS", []

    if cmd == "buy":
        if len(parts) < 3:
            print("uso: buy SYMBOL LOTS [sl] [tp]")
            return None
        return "TRADE_BUY", parts[1:5]

    if cmd == "sell":
        if len(parts) < 3:
            print("uso: sell SYMBOL LOTS [sl] [tp]")
            return None
        return "TRADE_SELL", parts[1:5]

    if cmd == "closeall":
        return "TRADE_CLOSE_ALL", []

    if cmd == "positions":
        return "TRADE_LIST", []

    print(f"comando desconhecido: {cmd} (digite help)")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="Caminho do MQL5\\Files (o EA imprime no log).")
    ap.add_argument("--timeout", type=float, default=6.0, help="timeout para aguardar resposta (segundos).")
    args = ap.parse_args()

    files_dir_str = maybe_wslpath(args.dir)
    files_dir = Path(files_dir_str)

    set_blue()
    print("MT5 CLI por arquivos (cmd_*.txt / resp_*.txt)")
    print("Dica: digite help")
    print(f"Files dir: {files_dir}")

    try:
        while True:
            try:
                line = input("mt> ")
            except (EOFError, KeyboardInterrupt):
                print("\nsaindo...")
                break

            line = line.strip()
            if not line:
                continue
            if line.lower() in ("quit", "exit"):
                break

            parsed = parse_user_line(line)
            if not parsed:
                continue

            cmd_type, params = parsed
            cmd_id = gen_id()

            try:
                write_cmd(files_dir, cmd_id, cmd_type, params)
                ok, msg, data = wait_resp(files_dir, cmd_id, timeout=args.timeout)

                print(("OK" if ok else "ERROR") + (f": {msg}" if msg else ""))
                for ln in data:
                    print("  " + ln)

            except Exception as e:
                print(f"ERROR: {e}")

    finally:
        reset_color()


if __name__ == "__main__":
    main()
