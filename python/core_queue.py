"""Fila/manual override por símbolo + last_seen."""

import time
import threading
from collections import defaultdict, deque

MAX_QUEUE_PER_SYMBOL = 50
lock = threading.Lock()
queues = defaultdict(deque)   # symbol -> deque de comandos
last_seen = {}                # symbol -> dict com info do EA


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


def status(symbol: str | None):
    with lock:
        if symbol:
            return last_seen.get(symbol.upper())
        return dict(last_seen)

