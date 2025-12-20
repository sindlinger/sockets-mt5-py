#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI unificado (interativo) com lógica separada de transporte.

Transporte:
  - socket (default): host/port -> gateway (9095) ou serviço MQL (9090)
  - file (opcional): dir cmd_/resp_ (modo cmdmt legado)

Formatos:
  - texto id|CMD|p1|p2...
  - json linha {"cmd": ...}

Comandos no prompt:
  ping
  open SYMBOL TF
  applytpl SYMBOL TF TEMPLATE
  list
  buy SYMBOL LOTS [sl=PTS] [tp=PTS]
  sell SYMBOL LOTS [sl=PTS] [tp=PTS]
  closeall
  positions
  raw <linha_completa>
  json <json_inteiro>
  quit
"""

import argparse
import json
import os
import random
import socket
import sys
import time
from pathlib import Path

# ---------------- Transportes ----------------
class TransportSocket:
    def __init__(self, host: str, port: int, timeout: float = 3.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    def send_text(self, line: str) -> str:
        if not line.endswith("\n"):
            line += "\n"
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as s:
            s.sendall(line.encode("utf-8"))
            data = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break
        return data.decode("utf-8", errors="ignore")

    def send_json(self, obj: dict) -> dict:
        line = json.dumps(obj) + "\n"
        resp = self.send_text(line)
        try:
            return json.loads(resp.strip())
        except Exception:
            return {"ok": False, "error": resp.strip()}


class TransportFile:
    """Modo legado por arquivos (cmd_/resp_)."""

    def __init__(self, directory: str, timeout: float = 6.0):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout

    def _gen_id(self) -> str:
        return f"{int(time.time()*1000)}_{random.randint(1000,9999)}"

    def send_text(self, line: str) -> str:
        cmd_id = self._gen_id()
        fname = self.dir / f"cmd_{cmd_id}.txt"
        with open(fname, "w", encoding="ascii", errors="ignore", newline="\n") as f:
            f.write(line.strip() + "\n")
        resp = self.dir / f"resp_{cmd_id}.txt"
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            if resp.exists():
                break
            time.sleep(0.05)
        if not resp.exists():
            return "ERROR\ntimeout\n"
        txt = resp.read_text(encoding="utf-8", errors="replace")
        try:
            resp.unlink()
        except Exception:
            pass
        return txt

    def send_json(self, obj: dict) -> dict:
        resp_txt = self.send_text(json.dumps(obj))
        try:
            return json.loads(resp_txt.strip())
        except Exception:
            return {"ok": False, "error": resp_txt.strip()}


# ---------------- Comandos ----------------
def build_text(cmd: str, args: list[str], cid: str) -> str:
    """Monta linha id|CMD|... em formato serviço MQL/gateway."""
    parts = [cid, cmd] + args
    return "|".join(parts)


def parse_user(line: str):
    parts = line.strip().split()
    if not parts:
        return None
    cmd = parts[0].lower()

    if cmd == "ping":
        return ("text", build_text("PING", [], cid_gen()), None)
    if cmd == "open" and len(parts) >= 3:
        return ("text", build_text("OPEN_CHART", [parts[1], parts[2]], cid_gen()), None)
    if cmd == "applytpl" and len(parts) >= 4:
        return ("text", build_text("APPLY_TPL", [parts[1], parts[2], parts[3]], cid_gen()), None)
    if cmd == "list":
        return ("text", build_text("LIST_CHARTS", [], cid_gen()), None)
    if cmd == "buy" and len(parts) >= 3:
        return ("text", build_text("TRADE_BUY", parts[1:5], cid_gen()), None)
    if cmd == "sell" and len(parts) >= 3:
        return ("text", build_text("TRADE_SELL", parts[1:5], cid_gen()), None)
    if cmd == "closeall":
        return ("text", build_text("TRADE_CLOSE_ALL", [], cid_gen()), None)
    if cmd == "positions":
        return ("text", build_text("TRADE_LIST", [], cid_gen()), None)
    if cmd == "raw":
        payload = line[len("raw "):].strip()
        return ("text", payload, None)
    if cmd == "json":
        payload = line[len("json "):].strip()
        try:
            obj = json.loads(payload)
            return ("json", None, obj)
        except Exception as e:
            return ("error", f"JSON inválido: {e}", None)
    if cmd == "quit":
        return ("quit", "", None)
    return ("error", "comando desconhecido", None)


def cid_gen():
    return str(int(time.time() * 1000) % 100000000)


# ---------------- CLI ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transport", choices=["socket", "file"], default="socket")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9095)
    ap.add_argument("--dir", help="quando transport=file, dir dos cmd_/resp_")
    args = ap.parse_args()

    if args.transport == "socket":
        transport = TransportSocket(args.host, args.port)
        print(f"CLI unificado -> socket {args.host}:{args.port}")
    else:
        if not args.dir:
            ap.error("--dir obrigatório quando transport=file")
        transport = TransportFile(args.dir)
        print(f"CLI unificado -> file dir {args.dir}")

    while True:
        try:
            line = input("cli> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nsaindo...")
            break

        if not line:
            continue
        parsed = parse_user(line)
        if not parsed:
            continue
        mode, text_payload, json_payload = parsed
        if mode == "quit":
            break
        if mode == "error":
            print(text_payload)
            continue

        if mode == "text":
            resp = transport.send_text(text_payload)
            print(resp.strip())
        elif mode == "json":
            resp = transport.send_json(json_payload)
            print(resp)


if __name__ == "__main__":
    main()
