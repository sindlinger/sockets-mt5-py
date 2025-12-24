#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Legacy wrapper. Use PyMql-CodeBridge/pyout/registry.py
"""

import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "PyMql-CodeBridge" / "pyout"
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import registry as _reg

REGISTRY = _reg.REGISTRY


def handle_request(req: dict) -> dict:
    return _reg.handle_request(req)


def handle_array(name: str, arr, dtype: str):
    return _reg.handle_array(name, arr, dtype)
