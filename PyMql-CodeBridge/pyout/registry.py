#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Registry do PyOutService.
- registra comandos JSON (PY_CALL)
- registra arrays (PY_ARRAY_CALL)
"""

from __future__ import annotations

import importlib
import os
import sys
from typing import Any, Callable

BASE_DIR = os.path.dirname(__file__)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import commands
import arrays


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


def _load_plugins(reg: CommandRegistry) -> None:
    mods = os.environ.get("PYBRIDGE_PLUGIN", "").strip()
    if not mods:
        return
    for name in [m.strip() for m in mods.replace(";", ",").split(",") if m.strip()]:
        mod = importlib.import_module(name)
        if hasattr(mod, "register"):
            mod.register(reg)


REGISTRY = CommandRegistry()
commands.register(REGISTRY)
arrays.register(REGISTRY)
_load_plugins(REGISTRY)


def handle_request(req: dict) -> dict:
    return REGISTRY.handle_request(req)


def handle_array(name: str, arr, dtype: str):
    return REGISTRY.handle_array(name, arr, dtype)
