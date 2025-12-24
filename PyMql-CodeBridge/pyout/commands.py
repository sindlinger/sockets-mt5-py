#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Comandos (PY_CALL) do PyOutService."""

import time


def _cmd_ping(req: dict) -> dict:
    return {"ok": True, "pong": True, "ts": time.time()}


def _cmd_echo(req: dict) -> dict:
    return {"ok": True, "data": req.get("data")}


def _cmd_signal(req: dict) -> dict:
    ma_fast = float(req.get("ma_fast", 0.0))
    ma_slow = float(req.get("ma_slow", 0.0))
    rsi = float(req.get("rsi", 50.0))
    action = "HOLD"
    if ma_fast > ma_slow and rsi < 70:
        action = "BUY"
    elif ma_fast < ma_slow and rsi > 30:
        action = "SELL"
    return {
        "ok": True,
        "action": action,
        "debug": {
            "ma_fast": ma_fast,
            "ma_slow": ma_slow,
            "rsi": rsi,
            "symbol": req.get("symbol"),
            "tf": req.get("tf"),
            "time": req.get("time"),
        },
    }


def register(reg) -> None:
    reg.add_cmd("ping", _cmd_ping)
    reg.add_cmd("echo", _cmd_echo)
    reg.add_cmd("signal", _cmd_signal)
