#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mini-SDK do Python-Bridge.

Uso:
  - Adicione novos comandos registrando funções no REGISTRY.
  - Opcional: defina PYBRIDGE_PLUGIN=meu_modulo (com função register(reg)).

O registry separa:
  - comandos JSON (PY_CALL) -> handle_request
  - arrays (PY_ARRAY_CALL)  -> handle_array
"""

from __future__ import annotations

import importlib
import os
import time
from typing import Any, Callable

try:
    import cupy as cp  # type: ignore
except Exception:
    cp = None
try:
    import numpy as np  # type: ignore
except Exception:
    np = None


def _bool(v: str) -> bool:
    return v.strip().lower() in ("1", "true", "yes", "y", "on")


def parse_name(name: str) -> tuple[str, dict[str, str]]:
    base, sep, tail = name.partition("?")
    opts: dict[str, str] = {}
    if not tail:
        return base, opts
    for part in tail.replace(";", "&").split("&"):
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        opts[k.strip().lower()] = v.strip()
    return base, opts


def _apply_window(arr, win: str):
    if not win or np is None:
        return arr
    n = arr.shape[0]
    if win == "hann":
        w = np.hanning(n)
    elif win == "hamming":
        w = np.hamming(n)
    elif win == "blackman":
        w = np.blackman(n)
    else:
        return arr
    return arr * w


def _fft_mag(arr, use_gpu: bool, half: bool):
    if use_gpu and cp is not None:
        x = cp.asarray(arr)
        y = cp.abs(cp.fft.rfft(x) if half else cp.fft.fft(x))
        return cp.asnumpy(y)
    if np is None:
        return arr
    return np.abs(np.fft.rfft(arr)) if half else np.abs(np.fft.fft(arr))


class CommandRegistry:
    def __init__(self) -> None:
        self._cmds: dict[str, Callable[[dict], dict]] = {}
        self._arrays: dict[str, Callable[[Any, dict[str, str], str], Any]] = {}

    def add_cmd(self, name: str, fn: Callable[[dict], dict]) -> None:
        self._cmds[name] = fn

    def add_array(self, base: str, fn: Callable[[Any, dict[str, str], str], Any]) -> None:
        self._arrays[base] = fn

    def handle_request(self, req: dict) -> dict:
        cmd = req.get("cmd")
        if not cmd or cmd not in self._cmds:
            return {"ok": False, "error": f"cmd desconhecido: {cmd}"}
        return self._cmds[cmd](req)

    def handle_array(self, name: str, arr, dtype: str):
        base, opts = parse_name(name)
        fn = self._arrays.get(base)
        if not fn:
            return arr
        return fn(arr, opts, dtype)


REGISTRY = CommandRegistry()


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


def _array_fft(arr, opts: dict[str, str], dtype: str):
    if np is None:
        return arr
    half = _bool(opts.get("half", "0"))
    log = _bool(opts.get("log", "0"))
    norm = _bool(opts.get("norm", "0"))
    win = opts.get("win", "")
    if "gpu" in opts:
        use_gpu = _bool(opts.get("gpu", "0"))
    elif "cpu" in opts:
        use_gpu = not _bool(opts.get("cpu", "0"))
    else:
        use_gpu = cp is not None
    arr = _apply_window(arr, win)
    out = _fft_mag(arr, use_gpu, half)
    if norm:
        maxv = float(out.max()) if out.size else 0.0
        if maxv > 0:
            out = out / maxv
    if log:
        out = np.log10(out + 1e-12)
    return out


def _array_fft_gpu(arr, opts: dict[str, str], dtype: str):
    opts = dict(opts)
    opts["gpu"] = "1"
    return _array_fft(arr, opts, dtype)


def _array_fft_cpu(arr, opts: dict[str, str], dtype: str):
    opts = dict(opts)
    opts["gpu"] = "0"
    return _array_fft(arr, opts, dtype)


def register_defaults(reg: CommandRegistry) -> None:
    reg.add_cmd("ping", _cmd_ping)
    reg.add_cmd("echo", _cmd_echo)
    reg.add_cmd("signal", _cmd_signal)
    reg.add_array("fft", _array_fft)
    reg.add_array("fft_gpu", _array_fft_gpu)
    reg.add_array("fft_cpu", _array_fft_cpu)


def _load_plugins(reg: CommandRegistry) -> None:
    mods = os.environ.get("PYBRIDGE_PLUGIN", "").strip()
    if not mods:
        return
    for name in [m.strip() for m in mods.replace(";", ",").split(",") if m.strip()]:
        mod = importlib.import_module(name)
        if hasattr(mod, "register"):
            mod.register(reg)


register_defaults(REGISTRY)
_load_plugins(REGISTRY)


def handle_request(req: dict) -> dict:
    return REGISTRY.handle_request(req)


def handle_array(name: str, arr, dtype: str):
    return REGISTRY.handle_array(name, arr, dtype)
