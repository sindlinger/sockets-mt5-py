#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File bridge para FFT:
- Lê arquivos em MQL5/Files:
    <base>_req.txt  (count, half, log, norm, win)
    <base>_req.bin  (double f64)
- Escreve:
    <base>_resp.bin (double f64)
"""
import os
import time
from pathlib import Path

try:
    import cupy as cp  # type: ignore
except Exception:
    cp = None
try:
    import numpy as np  # type: ignore
except Exception:
    np = None


def find_files_dir() -> Path:
    env = os.environ.get("MT5_FILES_DIR") or os.environ.get("CMDMT_MT5_FILES")
    if env:
        return Path(env)
    # tenta localizar Terminal mais recente
    candidates = []
    base = Path("/mnt/c/Users")
    for p in base.glob("*/AppData/Roaming/MetaQuotes/Terminal/*/MQL5/Files"):
        if p.is_dir():
            candidates.append(p)
    if not candidates:
        raise FileNotFoundError("MQL5/Files não encontrado. Defina MT5_FILES_DIR.")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def parse_req(text: str) -> dict:
    out = {"count": 0, "half": False, "log": False, "norm": False, "win": ""}
    for part in text.replace("\n", ";").split(";"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        k = k.strip().lower()
        v = v.strip().lower()
        if k == "count":
            try:
                out["count"] = int(v)
            except Exception:
                out["count"] = 0
        elif k in ("half", "log", "norm"):
            out[k] = v in ("1", "true", "yes", "y", "on")
        elif k == "win":
            out["win"] = v
    return out


def apply_window(arr, win: str):
    if not win:
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


def fft_mag(arr, use_gpu: bool, half: bool):
    if use_gpu and cp is not None:
        x = cp.asarray(arr)
        if half:
            y = cp.abs(cp.fft.rfft(x))
        else:
            y = cp.abs(cp.fft.fft(x))
        return cp.asnumpy(y)
    if half:
        return np.abs(np.fft.rfft(arr))
    return np.abs(np.fft.fft(arr))


def main():
    if np is None:
        raise RuntimeError("numpy não disponível")

    files_dir = find_files_dir()
    base = os.environ.get("PYFFT_BASE", "pyfft")
    req_txt = files_dir / f"{base}_req.txt"
    req_bin = files_dir / f"{base}_req.bin"
    resp_bin = files_dir / f"{base}_resp.bin"

    while True:
        if req_txt.exists() and req_bin.exists():
            try:
                text = req_txt.read_text(encoding="utf-8", errors="ignore")
                opts = parse_req(text)
                count = int(opts.get("count", 0))
                if count <= 0:
                    time.sleep(0.1)
                    continue
                raw = req_bin.read_bytes()
                arr = np.frombuffer(raw, dtype=np.float64, count=count)
                arr = apply_window(arr, opts.get("win", ""))
                out = fft_mag(arr, cp is not None, opts.get("half", False))
                if opts.get("norm", False):
                    maxv = float(out.max()) if out.size else 0.0
                    if maxv > 0:
                        out = out / maxv
                if opts.get("log", False):
                    out = np.log10(out + 1e-12)
                out.astype(np.float64, copy=False).tofile(resp_bin)
                try:
                    req_txt.unlink()
                    req_bin.unlink()
                except Exception:
                    pass
            except Exception:
                time.sleep(0.1)
        else:
            time.sleep(0.1)


if __name__ == "__main__":
    main()

