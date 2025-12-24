#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Arrays (PY_ARRAY_CALL) do PyOutService."""

try:
    import cupy as cp  # type: ignore
except Exception:
    cp = None
try:
    import cupyx.scipy.signal as cpsig  # type: ignore
except Exception:
    cpsig = None
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


def _float_opt(opts: dict[str, str], key: str, default: float) -> float:
    try:
        return float(opts.get(key, str(default)))
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
    if cp is None or cpsig is None:
        raise RuntimeError("cupy/cupyx not available")
    total = int(arr.shape[0])
    if total <= 0:
        return arr

    n = _int_opt(opts, "n", total)
    if n <= 0 or n > total:
        n = total
    hop = _int_opt(opts, "hop", 0)
    noverlap = _int_opt(opts, "noverlap", -1)
    if hop > 0:
        noverlap = max(0, n - hop)
    if noverlap < 0:
        noverlap = n // 2

    nfft = _int_opt(opts, "nfft", 0)
    nfft = nfft if nfft > 0 else None

    window = opts.get("window", "") or opts.get("win", "") or "hann"
    onesided = _bool(opts.get("onesided", opts.get("half", "1")))
    boundary = opts.get("boundary", "none").strip().lower()
    if boundary in ("none", "null", "false", "0"):
        boundary = None
    padded = _bool(opts.get("padded", "0"))
    scaling = (opts.get("scaling", "") or "spectrum").strip().lower()
    fs = _float_opt(opts, "fs", 1.0)
    spb = _float_opt(opts, "spb", 0.0)

    x = cp.asarray(arr, dtype=cp.float64)
    _, _, Zxx = cpsig.stft(
        x,
        fs=fs,
        window=window,
        nperseg=n,
        noverlap=noverlap,
        nfft=nfft,
        detrend=False,
        return_onesided=onesided,
        boundary=boundary,
        padded=padded,
        axis=-1,
        scaling=scaling,
    )

    if Zxx.size == 0:
        return cp.asnumpy(cp.zeros((0,), dtype=cp.float64))

    Zmean = cp.mean(Zxx, axis=-1)
    power = cp.abs(Zmean) ** 2
    phase = cp.unwrap(cp.angle(Zmean))

    bins = int(power.shape[0])
    if bins <= 0:
        return cp.asnumpy(power.astype(cp.float64))

    max_n = min(n, bins)
    if max_n <= 0:
        return cp.asnumpy(power.astype(cp.float64))

    delta_omega = 2.0 * cp.pi / float(max_n)
    dphi = cp.zeros_like(phase)
    if bins >= 2:
        dphi[1:-1] = (phase[2:] - phase[:-2]) / 2.0
        dphi[0] = phase[1] - phase[0]
        dphi[-1] = phase[-1] - phase[-2]

    tau_g = -(dphi / delta_omega)

    k = cp.arange(bins, dtype=cp.float64)
    period_bars = cp.where(k > 0, n / k, 0.0)
    max_eta_bars = period_bars * 1.5
    tau_g = cp.clip(tau_g, -max_eta_bars, max_eta_bars)

    eta_seconds = cp.abs(tau_g) * spb
    max_eta_seconds = period_bars * spb * 1.5
    eta_seconds = cp.where(max_eta_seconds > 0, cp.minimum(eta_seconds, max_eta_seconds), eta_seconds)

    out_bins = n // 2
    if out_bins <= 0 or out_bins > bins:
        out_bins = bins
    power = power[:out_bins]
    eta_seconds = eta_seconds[:out_bins]

    out = cp.concatenate([power, eta_seconds]).astype(cp.float64)
    return cp.asnumpy(out)


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
