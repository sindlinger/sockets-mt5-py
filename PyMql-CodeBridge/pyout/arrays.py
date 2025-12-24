#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Arrays (PY_ARRAY_CALL) do PyOutService."""

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


def _int_opt(opts: dict[str, str], key: str, default: int) -> int:
    try:
        return int(opts.get(key, str(default)))
    except Exception:
        return default


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


def _array_stfft(arr, opts: dict[str, str], dtype: str):
    if np is None:
        return arr
    total = int(arr.shape[0])
    if total <= 0:
        return arr
    win_n = _int_opt(opts, "n", 0)
    hop = _int_opt(opts, "hop", 0)
    if win_n <= 0 or win_n > total:
        win_n = total
    if hop <= 0:
        hop = max(1, win_n // 2)
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

    win_arr = None
    if win and np is not None:
        win_arr = _apply_window(np.ones(win_n, dtype=np.float64), win)

    out_acc = None
    count = 0
    i = 0
    last = total - win_n
    while i <= last:
        seg = arr[i : i + win_n]
        if win_arr is not None:
            seg = seg * win_arr
        if use_gpu and cp is not None:
            x = cp.asarray(seg)
            y = cp.abs(cp.fft.rfft(x) if half else cp.fft.fft(x))
            y = cp.asnumpy(y)
        else:
            y = np.abs(np.fft.rfft(seg)) if half else np.abs(np.fft.fft(seg))
        if out_acc is None:
            out_acc = y
        else:
            out_acc = out_acc + y
        count += 1
        i += hop

    if out_acc is None:
        out = np.zeros(win_n // 2 + 1 if half else win_n, dtype=np.float64)
    else:
        out = out_acc / float(max(1, count))
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


def register(reg) -> None:
    reg.add_array("fft", _array_fft)
    reg.add_array("stfft", _array_stfft)
    reg.add_array("stft", _array_stfft)
    reg.add_array("fft_gpu", _array_fft_gpu)
    reg.add_array("fft_cpu", _array_fft_cpu)
