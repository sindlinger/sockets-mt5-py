#!/usr/bin/env python3
import socket
import sys
import struct
import threading
import time
import traceback
from urllib.parse import parse_qs

try:
    import cupy as cp
    _XP = cp
    _GPU = True
except Exception:
    import numpy as np
    _XP = np
    _GPU = False

import numpy as np

HOST = "0.0.0.0"
PORT = 9200

DTYPE_MAP = {
    "f64": np.dtype("<f8"),
    "f32": np.dtype("<f4"),
    "i32": np.dtype("<i4"),
    "i16": np.dtype("<i2"),
    "u8": np.dtype("u1"),
}

_jobs = {}
_jobs_lock = threading.Lock()


def log(msg):
    print("[PyOutCuPy]", msg, flush=True)


def recv_exact(conn, n):
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def recv_message(conn):
    first = conn.recv(1)
    if not first:
        return None
    if first == b"\xff":
        # frame
        lenbuf = recv_exact(conn, 4)
        if lenbuf is None:
            return None
        hdr_len = struct.unpack(">I", lenbuf)[0]
        header = recv_exact(conn, hdr_len)
        if header is None:
            return None
        header_str = header.decode("utf-8", errors="ignore")
        parts = header_str.split("|")
        payload = b""
        if len(parts) >= 6:
            try:
                raw_len = int(parts[5])
            except Exception:
                raw_len = 0
            if raw_len > 0:
                payload = recv_exact(conn, raw_len)
                if payload is None:
                    return None
        return ("frame", header_str, payload)

    # line (text)
    buf = bytearray()
    buf.extend(first)
    while True:
        ch = conn.recv(1)
        if not ch:
            break
        buf.extend(ch)
        if ch == b"\n":
            break
    line = buf.decode("utf-8", errors="ignore")
    return ("line", line)


def send_frame(conn, header, payload=b""):
    hb = header.encode("utf-8")
    prefix = b"\xff" + struct.pack(">I", len(hb))
    conn.sendall(prefix)
    conn.sendall(hb)
    if payload:
        conn.sendall(payload)


def send_line(conn, text):
    if not text.endswith("\n"):
        text += "\n"
    conn.sendall(text.encode("utf-8"))


def bytes_to_array(payload, dtype):
    dt = DTYPE_MAP.get(dtype, DTYPE_MAP["f64"])
    return np.frombuffer(payload, dtype=dt)


def array_to_bytes(arr):
    arr = np.asarray(arr, dtype=DTYPE_MAP["f64"])
    return arr.tobytes()


def _window(name, n):
    name = (name or "boxcar").lower()
    if name in ("boxcar", "rect", "rectangular", "none"):
        w = np.ones(n, dtype=np.float64)
    elif name in ("hann", "hanning"):
        w = np.hanning(n)
    elif name in ("hamming",):
        w = np.hamming(n)
    elif name in ("blackman",):
        w = np.blackman(n)
    elif name in ("bartlett",):
        w = np.bartlett(n)
    else:
        w = np.ones(n, dtype=np.float64)
    if _GPU:
        return cp.asarray(w)
    return w


def stfft_cmd(x, params):
    # parse parameters
    n = int(params.get("n", [len(x)])[0])
    nfft = int(params.get("nfft", [n])[0])
    window = params.get("window", ["boxcar"])[0]
    onesided = int(params.get("onesided", [1])[0])
    scaling = params.get("scaling", ["spectrum"])[0]
    spb = float(params.get("spb", [1.0])[0])

    xp = _XP
    x = xp.asarray(x, dtype=xp.float64)

    if n != x.size:
        if x.size > n:
            x = x[-n:]
        else:
            pad = xp.zeros(n - x.size, dtype=xp.float64)
            x = xp.concatenate([pad, x])

    w = _window(window, n)
    xw = x * w

    if onesided:
        X = xp.fft.rfft(xw, nfft)
        # expected size: nfft//2 + 1. MT5 expects n/2 (exclude Nyquist)
        kmax = nfft // 2
        X = X[:kmax]
        power = xp.abs(X) ** 2
        if scaling == "spectrum":
            power = power / float(nfft)
        freq = xp.arange(kmax, dtype=xp.float64) / (float(nfft) * spb)
    else:
        X = xp.fft.fft(xw, nfft)
        power = xp.abs(X) ** 2
        freq = xp.fft.fftfreq(nfft, d=spb)

    # eta in seconds (period). avoid division by zero
    eta = xp.zeros_like(freq)
    if freq.size > 1:
        eta[1:] = 1.0 / freq[1:]

    # Return [power..., eta...] length = kmax*2
    out = xp.concatenate([power.astype(xp.float64), eta.astype(xp.float64)])
    if _GPU:
        out = cp.asnumpy(out)
    return out


def dispatch_array(func, x):
    # func can include query string e.g. stfft?n=256&...
    if "?" in func:
        name, qs = func.split("?", 1)
        params = parse_qs(qs)
    else:
        name, params = func, {}
    name = name.strip().lower()

    if name == "stfft":
        return stfft_cmd(x, params)

    # fallback: echo input
    return np.asarray(x, dtype=np.float64)


def handle_frame(conn, header, payload):
    parts = header.split("|")
    if len(parts) < 6:
        return
    req_id = parts[0]
    cmd = parts[1]

    if cmd == "PY_ARRAY_CALL":
        name = parts[2]
        dtype = parts[3]
        count = int(parts[4])
        # raw_len = int(parts[5])
        x = bytes_to_array(payload, dtype)
        if count > 0:
            x = x[:count]
        try:
            out = dispatch_array(name, x)
            out_bytes = array_to_bytes(out)
            out_count = len(out_bytes) // 8
            resp_h = f"{req_id}|PY_ARRAY_RESP|{name}|f64|{out_count}|{len(out_bytes)}"
            send_frame(conn, resp_h, out_bytes)
        except Exception as e:
            msg = str(e)
            resp_h = f"{req_id}|PY_ARRAY_ERROR|0|txt|0|{len(msg)}"
            send_frame(conn, resp_h, msg.encode("utf-8"))
        return

    if cmd == "PY_ARRAY_SUBMIT":
        name = parts[2]
        dtype = parts[3]
        count = int(parts[4])
        x = bytes_to_array(payload, dtype)
        if count > 0:
            x = x[:count]
        job_id = str(int(time.time() * 1000000))

        def worker():
            try:
                out = dispatch_array(name, x)
                out_bytes = array_to_bytes(out)
                with _jobs_lock:
                    _jobs[job_id] = ("done", out_bytes)
            except Exception as ex:
                with _jobs_lock:
                    _jobs[job_id] = ("error", str(ex))

        with _jobs_lock:
            _jobs[job_id] = ("pending", None)
        threading.Thread(target=worker, daemon=True).start()

        resp_h = f"{req_id}|PY_ARRAY_ACK|{job_id}|txt|0|0"
        send_frame(conn, resp_h, b"")
        return

    if cmd == "PY_ARRAY_POLL":
        job_id = parts[2]
        with _jobs_lock:
            status, payload_or_msg = _jobs.get(job_id, ("pending", None))
        if status == "pending":
            resp_h = f"{req_id}|PY_ARRAY_PENDING|{job_id}|txt|0|0"
            send_frame(conn, resp_h, b"")
        elif status == "done":
            out_bytes = payload_or_msg
            out_count = len(out_bytes) // 8
            resp_h = f"{req_id}|PY_ARRAY_RESP|{job_id}|f64|{out_count}|{len(out_bytes)}"
            send_frame(conn, resp_h, out_bytes)
        else:
            msg = payload_or_msg or "error"
            resp_h = f"{req_id}|PY_ARRAY_ERROR|{job_id}|txt|0|{len(msg)}"
            send_frame(conn, resp_h, msg.encode("utf-8"))
        return


def handle_line(conn, line):
    # PyInService sends only the payload string (no id/type here)
    line = line.strip()
    if not line:
        send_line(conn, "")
        return
    if line.upper() == "PING":
        send_line(conn, "PONG")
        return
    # return echo as JSON-like string
    send_line(conn, line)


def serve(host, port):
    log(f"GPU enabled: {_GPU}")
    log(f"Listening on {host}:{port}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.listen(1)
        while True:
            conn, addr = s.accept()
            log(f"Client connected: {addr}")
            with conn:
                while True:
                    msg = recv_message(conn)
                    if msg is None:
                        break
                    mtype, *rest = msg
                    if mtype == "frame":
                        header, payload = rest
                        handle_frame(conn, header, payload)
                    else:
                        line = rest[0]
                        handle_line(conn, line)
            log("Client disconnected")


if __name__ == "__main__":
    host = HOST
    port = PORT
    if len(sys.argv) >= 2:
        host = sys.argv[1]
    if len(sys.argv) >= 3:
        port = int(sys.argv[2])
    serve(host, port)
