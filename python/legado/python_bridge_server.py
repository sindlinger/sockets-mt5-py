#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Legacy wrapper. Use PyMql-CodeBridge/pyout/pyout_server.py
"""

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "PyMql-CodeBridge" / "pyout"
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import pyout_server

if __name__ == "__main__":
    pyout_server.main()
