#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gateway socket único (porta 9095)
- Proxy texto id|CMD|... para serviço MQL em host.docker.internal:9090 (fallback 127.0.0.1)
- JSON linha (ping/echo/signal/ew_analyze/mql_raw)
- Fila/manual override por símbolo (buy/sell/close/hold/queue/status)

Handshake:
- Se receber linha "HELLO <ROLE>", ignora (não responde).
"""

import json
import os
import socketserver
import time
import threading
from collections import defaultdict, deque

from core_mql_proxy import send_line as mql_send

HOST = os.environ.get("GW_HOST", "0.0.0.0")
PORT = int(os.environ.get("GW_PORT", "9095"))

MAX_QUEUE_PER_SYMBOL = 50

lock = threading.Lock()
queues = defaultdict(deque)   # symbol -> deque de comandos
last_seen = {}                # symbol -> dict com info do EA

# Adaptador de ondas (opcional)
try:
    import ew_adapter
except Exception:
    ew_adapter = None


def _qsize(symbol: str) -> int:
    return len(queues[symbol])


def push_cmd(symbol: str, payload: dict) -> dict:
    symbol = symbol.upper()
    with lock:
        if len(queues[symbol]) >= MAX_QUEUE_PER_SYMBOL:
            return {"ok": False, "error": f"fila cheia para {symbol} (max={MAX_QUEUE_PER_SYMBOL})"}
        queues[symbol].append(payload)
        return {"ok": True, "queued": len(queues[symbol]), "symbol": symbol, **payload}


def pop_cmd(symbol: str):
    symbol = symbol.upper()
    with lock:
        if queues[symbol]:
            return queues[symbol].popleft()
    return None


def clear_queue(symbol: str) -> dict:
    symbol = symbol.upper()
    with lock:
        n = len(queues[symbol])
        queues[symbol].clear()
    return {"ok": True, "cleared": n, "symbol": symbol}


def set_last_seen(symbol: str, req: dict):
    symbol = symbol.upper()
    with lock:
        last_seen[symbol] = {
            "ts": time.time(),
            "symbol": symbol,
            "tf": req.get("tf"),
            "time": req.get("time"),
            "bid": req.get("bid"),
            "ask": req.get("ask"),
            "equity": req.get("equity"),
            "free_margin": req.get("free_margin"),
            "pos": req.get("pos"),
        }


def parse_kv(tokens):
    out = {}
    for t in tokens:
        if "=" in t:
            k, v = t.split("=", 1)
            out[k.strip().lower()] = v.strip()
    return out


def handle_text(line: str) -> dict:
    line = line.strip()
    if not line:
        return {"ok": False, "error": "linha vazia"}

    if line.upper().startswith("HELLO "):
        return {"_ignore": True}

    # Proxy direto se já veio no formato id|CMD
    if "|" in line:
        ok, resp = mql_send(line)
        return {"ok": ok, "resp": resp}

    parts = line.split()
    cmd = parts[0].lower()

    if cmd == "ping":
        return {"ok": True, "pong": True, "ts": time.time()}

    if cmd == "help":
        return {"ok": True, "help": [
            "buy BTCUSD 0.01 sl=500 tp=1000",
            "sell BTCUSD 0.01 sl=500 tp=1000",
            "close BTCUSD",
            "hold BTCUSD",
            "queue BTCUSD",
            "cancel BTCUSD",
            "status [BTCUSD]",
            "ping",
        ]}

    if cmd in ("buy", "sell"):
        if len(parts) < 3:
            return {"ok": False, "error": "use: buy|sell SYMBOL LOTS [sl=PTS] [tp=PTS]"}
        symbol = parts[1].upper()
        lots = float(parts[2])
        kv = parse_kv(parts[3:])
        payload = {"action": cmd.upper(), "lots": lots}
        if "sl" in kv:
            payload["sl_points"] = int(float(kv["sl"]))
        if "tp" in kv:
            payload["tp_points"] = int(float(kv["tp"]))
        return push_cmd(symbol, payload)

    if cmd in ("close", "hold"):
        if len(parts) < 2:
            return {"ok": False, "error": "use: close|hold SYMBOL"}
        symbol = parts[1].upper()
        return push_cmd(symbol, {"action": cmd.upper()})

    if cmd == "queue":
        if len(parts) < 2:
            return {"ok": False, "error": "use: queue SYMBOL"}
        symbol = parts[1].upper()
        return {"ok": True, "symbol": symbol, "queued": _qsize(symbol)}

    if cmd in ("cancel", "clear"):
        if len(parts) < 2:
            return {"ok": False, "error": "use: cancel SYMBOL"}
        return clear_queue(parts[1])

    if cmd == "status":
        symbol = parts[1].upper() if len(parts) >= 2 else None
        st = status(symbol)
        return {"ok": True, "status": st}

    return {"ok": False, "error": f"comando desconhecido: {cmd}"}


def status(symbol: str | None):
    if not symbol:
        with lock:
            summary = {}
            for sym, st in last_seen.items():
                summary[sym] = {"ts": st.get("ts"), "tf": st.get("tf"), "time": st.get("time")}
            q = {sym: len(q) for sym, q in queues.items() if len(q) > 0}
        return {"status": summary, "queues": q}
    with lock:
        return {"status": last_seen.get(symbol.upper()), "queued": _qsize(symbol)}


def handle_json(req: dict) -> dict:
    cmd = req.get("cmd")

    if cmd == "ping":
        return {"ok": True, "pong": True, "ts": time.time()}

    if cmd == "echo":
        return {"ok": True, "data": req.get("data")}

    if cmd == "signal":
        symbol = (req.get("symbol") or "UNKNOWN").upper()
        set_last_seen(symbol, req)
        manual = pop_cmd(symbol)
        if manual:
            return {"ok": True, **manual, "source": "manual"}
        return {"ok": True, "action": "HOLD", "source": "auto"}

    if cmd in ("ew_analyze", "EW_ANALYZE"):
        if ew_adapter is None:
            return {"ok": False, "error": "ew_adapter não importado"}
        try:
            bars = req.get("bars") or []
            params = req.get("params") or {}
            res = ew_adapter.analyze(bars, params)
            return {"ok": True, "waves": res.get("waves", []), "summary": res.get("summary", {})}
        except Exception as e:
            return {"ok": False, "error": f"ew_analyze fail: {e}"}

    if cmd == "mql_raw":
        line = req.get("line", "")
        ok, resp = mql_send(line)
        return {"ok": ok, "resp": resp}

    return {"ok": False, "error": f"cmd desconhecido: {cmd}"}


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        while True:
            raw = self.rfile.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            try:
                if line.startswith("{"):
                    req = json.loads(line)
                    resp = handle_json(req)
                else:
                    resp = handle_text(line)
            except Exception as e:
                resp = {"ok": False, "error": str(e)}

            if resp.get("_ignore"):
                continue

            self.wfile.write((json.dumps(resp) + "\n").encode("utf-8"))
            self.wfile.flush()


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    with ThreadedTCPServer((HOST, PORT), Handler) as srv:
        print(f"Gateway escutando em {HOST}:{PORT} -> proxy MQL host.docker.internal:9090")
        srv.serve_forever()


if __name__ == "__main__":
    main()
