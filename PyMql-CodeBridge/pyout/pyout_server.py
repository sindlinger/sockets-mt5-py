#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyOutService (pyout) para MT5.
Modo default: conecta no Gateway (porta unica) e responde PY_CALL / PY_ARRAY_CALL.
Modo alternativo: servidor dedicado (legacy).

Env vars:
  PYBRIDGE_MODE=gate|gateway|server
  PYBRIDGE_HOST / PYBRIDGE_PORT (modo server)
  GW_HOSTS / GW_PORT           (modo gateway)
"""

import json
import os
import socket
import socketserver
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
import threading

BASE_DIR = os.path.dirname(__file__)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import registry as reg

try:
    import numpy as np  # type: ignore
except Exception:
    np = None

MODE = os.environ.get("PYBRIDGE_MODE", "server").lower()
HOST = os.environ.get("PYBRIDGE_HOST", "0.0.0.0")
PORT = int(os.environ.get("PYBRIDGE_PORT", "9100"))
GW_HOSTS = os.environ.get("GW_HOSTS", "host.docker.internal,127.0.0.1")
GW_PORT = int(os.environ.get("GW_PORT", "9095"))
LOG_ENABLED = os.environ.get("PYOUT_LOG", "1").lower() not in ("0", "false", "no", "off")
WORKERS = max(1, int(os.environ.get("PYOUT_WORKERS", "2")))

# armazena ultimo array recebido
LAST_ARRAY = {"name": "", "dtype": "", "count": 0, "data": b""}

# jobs async
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
EXECUTOR = ThreadPoolExecutor(max_workers=WORKERS)


def _process_array_job(name: str, dtype: str, count: int, payload: bytes):
    dt = _dtype_to_numpy(dtype)
    if dt is None or np is None:
        return dtype, count, payload

    arr = np.frombuffer(payload, dtype=dt, count=count)
    out = reg.handle_array(name, arr, dtype)
    if np is None:
        out_arr = arr
    else:
        out_arr = np.asarray(out, dtype=dt)

    out_bytes = out_arr.tobytes()
    return dtype, len(out_arr), out_bytes


def _jobs_cleanup(now: float, ttl: float = 120.0) -> None:
    with JOBS_LOCK:
        stale = [k for k, v in JOBS.items() if now - v.get("created", now) > ttl]
        for k in stale:
            JOBS.pop(k, None)


def submit_job(name: str, dtype: str, count: int, payload: bytes) -> str:
    job_id = uuid.uuid4().hex
    fut = EXECUTOR.submit(_process_array_job, name, dtype, count, payload)
    with JOBS_LOCK:
        JOBS[job_id] = {
            "future": fut,
            "created": time.time(),
        }
    return job_id


def poll_job(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return "not_found", "", 0, b"", "job_not_found"

    fut = job["future"]
    if not fut.done():
        return "pending", "", 0, b"", ""

    try:
        dtype, out_count, out_bytes = fut.result()
    except Exception as e:
        with JOBS_LOCK:
            JOBS.pop(job_id, None)
        return "error", "", 0, b"", str(e)

    with JOBS_LOCK:
        JOBS.pop(job_id, None)
    return "done", dtype, out_count, out_bytes, ""


def log(msg: str) -> None:
    if LOG_ENABLED:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] [PyOut] {msg}", flush=True)


def log_frame(tag: str, header_text: str) -> None:
    if not header_text:
        log(f"{tag} header=(empty)")
    else:
        log(f"{tag} header={header_text}")


def handle_request(req: dict) -> dict:
    return reg.handle_request(req)


# ----------------- Frame helpers -----------------

def recv_exact(sock: socket.socket, n: int) -> bytes:
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            return b""
        data += chunk
    return data


def read_message(sock: socket.socket, buf_holder: dict):
    buf = buf_holder.get("buf", b"")
    if not buf:
        chunk = sock.recv(4096)
        if not chunk:
            return None
        buf = chunk
    if buf[0] == 0xFF:
        while len(buf) < 5:
            chunk = sock.recv(4096)
            if not chunk:
                return None
            buf += chunk
        hdr_len = int.from_bytes(buf[1:5], "big")
        total = 5 + hdr_len
        while len(buf) < total:
            chunk = sock.recv(4096)
            if not chunk:
                return None
            buf += chunk
        header = buf[5:5 + hdr_len]
        header_text = header.decode("utf-8", "ignore")
        raw_len = 0
        try:
            parts = header_text.split("|")
            if len(parts) >= 6:
                raw_len = int(parts[5])
        except Exception:
            raw_len = 0
        total = 5 + hdr_len + raw_len
        while len(buf) < total:
            chunk = sock.recv(4096)
            if not chunk:
                return None
            buf += chunk
        frame = buf[:total]
        buf_holder["buf"] = buf[total:]
        return ("frame", frame, header_text)

    while b"\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            if not buf:
                return None
            line = buf
            buf_holder["buf"] = b""
            return ("line", line.decode("utf-8", "replace"), None)
        buf += chunk
    idx = buf.find(b"\n")
    line = buf[:idx]
    buf_holder["buf"] = buf[idx + 1:]
    return ("line", line.decode("utf-8", "replace"), None)


def _dtype_to_numpy(dtype: str):
    if dtype == "f64":
        return np.float64 if np else None
    if dtype == "f32":
        return np.float32 if np else None
    if dtype == "i32":
        return np.int32 if np else None
    if dtype == "i16":
        return np.int16 if np else None
    if dtype == "u8":
        return np.uint8 if np else None
    return None


def handle_frame(frame: bytes, header_text: str) -> bytes:
    log_frame("RX", header_text)
    parts = header_text.split("|")
    if len(parts) >= 6 and parts[1] == "PY_ARRAY_SUBMIT":
        name = parts[2]
        dtype = parts[3]
        count = int(parts[4])
        raw_len = int(parts[5])
        payload = frame[-raw_len:] if raw_len > 0 else b""
        log(f"PY_ARRAY_SUBMIT name={name} dtype={dtype} count={count} raw_len={raw_len}")

        job_id = submit_job(name, dtype, count, payload)
        resp_header = f"{parts[0]}|PY_ARRAY_ACK|{job_id}|{dtype}|0|0"
        hb = resp_header.encode("utf-8")
        return b"\xFF" + len(hb).to_bytes(4, "big") + hb

    if len(parts) >= 6 and parts[1] == "PY_ARRAY_POLL":
        job_id = parts[2]
        status, dtype, out_count, out_bytes, err = poll_job(job_id)
        if status == "pending":
            resp_header = f"{parts[0]}|PY_ARRAY_PENDING|{job_id}|{dtype}|0|0"
            hb = resp_header.encode("utf-8")
            return b"\xFF" + len(hb).to_bytes(4, "big") + hb
        if status == "done":
            resp_header = f"{parts[0]}|PY_ARRAY_RESP|{job_id}|{dtype}|{out_count}|{len(out_bytes)}"
            hb = resp_header.encode("utf-8")
            return b"\xFF" + len(hb).to_bytes(4, "big") + hb + out_bytes

        err_bytes = (err or "py_error").encode("utf-8")
        resp_header = f"{parts[0]}|PY_ARRAY_ERROR|{job_id}|txt|0|{len(err_bytes)}"
        hb = resp_header.encode("utf-8")
        return b"\xFF" + len(hb).to_bytes(4, "big") + hb + err_bytes

    if len(parts) >= 6 and parts[1] == "PY_ARRAY_CALL":
        name = parts[2]
        dtype = parts[3]
        count = int(parts[4])
        raw_len = int(parts[5])
        payload = frame[-raw_len:] if raw_len > 0 else b""
        log(f"PY_ARRAY_CALL name={name} dtype={dtype} count={count} raw_len={raw_len}")

        LAST_ARRAY["name"] = name
        LAST_ARRAY["dtype"] = dtype
        LAST_ARRAY["count"] = count
        LAST_ARRAY["data"] = payload

        dt = _dtype_to_numpy(dtype)
        if dt is None or np is None:
            resp_header = f"{parts[0]}|PY_ARRAY_RESP|{name}|{dtype}|{count}|{raw_len}"
            hb = resp_header.encode("utf-8")
            return b"\xFF" + len(hb).to_bytes(4, "big") + hb + payload

        arr = np.frombuffer(payload, dtype=dt, count=count)
        try:
            out = reg.handle_array(name, arr, dtype)
        except Exception:
            out = arr

        if np is None:
            out = arr
        else:
            out = np.asarray(out, dtype=dt)

        out_bytes = out.tobytes()
        resp_header = f"{parts[0]}|PY_ARRAY_RESP|{name}|{dtype}|{len(out)}|{len(out_bytes)}"
        hb = resp_header.encode("utf-8")
        log(f"PY_ARRAY_RESP name={name} dtype={dtype} count={len(out)} raw_len={len(out_bytes)}")
        return b"\xFF" + len(hb).to_bytes(4, "big") + hb + out_bytes
    return b""


# ----------------- Gateway client -----------------

def connect_gateway():
    hosts = [h.strip() for h in GW_HOSTS.replace(";", ",").split(",") if h.strip()]
    last_err = None
    for h in hosts:
        try:
            s = socket.create_connection((h, GW_PORT), timeout=3)
            s.sendall(b"HELLO PY\n")
            return s
        except Exception as e:
            last_err = e
    raise last_err


def run_gateway_client():
    while True:
        try:
            sock = connect_gateway()
        except Exception:
            time.sleep(1.0)
            continue

        buf_holder = {"buf": b""}
        try:
            while True:
                msg = read_message(sock, buf_holder)
                if not msg:
                    break
                kind, payload, header = msg
                if kind == "frame":
                    resp = handle_frame(payload, header or "")
                    if resp:
                        sock.sendall(resp)
                else:
                    line = payload.strip()
                    if not line:
                        continue
                    log(f"RX PY_CALL json_len={len(line)}")
                    try:
                        req = json.loads(line)
                        resp = handle_request(req)
                    except Exception as e:
                        resp = {"ok": False, "error": str(e)}
                    sock.sendall((json.dumps(resp) + "\n").encode("utf-8"))
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass
        time.sleep(1.0)


# ----------------- Server (legacy) -----------------
class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        while True:
            first = self.rfile.read(1)
            if not first:
                break
            if first == b"\xFF":
                hdr_len = int.from_bytes(self.rfile.read(4), "big")
                header = self.rfile.read(hdr_len).decode("utf-8", "ignore")
                parts = header.split("|")
                if len(parts) >= 6 and parts[1] == "PY_ARRAY_SUBMIT":
                    name = parts[2]
                    dtype = parts[3]
                    count = int(parts[4])
                    raw_len = int(parts[5])
                    payload = self.rfile.read(raw_len) if raw_len > 0 else b""
                    log_frame("RX", header)
                    log(f"PY_ARRAY_SUBMIT name={name} dtype={dtype} count={count} raw_len={raw_len}")

                    job_id = submit_job(name, dtype, count, payload)
                    resp_header = f"{parts[0]}|PY_ARRAY_ACK|{job_id}|{dtype}|0|0"
                    hb = resp_header.encode("utf-8")
                    frame = b"\xFF" + len(hb).to_bytes(4, "big") + hb
                    self.wfile.write(frame)
                    self.wfile.flush()
                    log_frame("TX", resp_header)
                    continue

                if len(parts) >= 6 and parts[1] == "PY_ARRAY_POLL":
                    job_id = parts[2]
                    status, dtype, out_count, out_bytes, err = poll_job(job_id)
                    if status == "pending":
                        resp_header = f"{parts[0]}|PY_ARRAY_PENDING|{job_id}|{dtype}|0|0"
                        hb = resp_header.encode("utf-8")
                        frame = b"\xFF" + len(hb).to_bytes(4, "big") + hb
                        self.wfile.write(frame)
                        self.wfile.flush()
                        log_frame("TX", resp_header)
                        continue
                    if status == "done":
                        resp_header = f"{parts[0]}|PY_ARRAY_RESP|{job_id}|{dtype}|{out_count}|{len(out_bytes)}"
                        hb = resp_header.encode("utf-8")
                        frame = b"\xFF" + len(hb).to_bytes(4, "big") + hb + out_bytes
                        self.wfile.write(frame)
                        self.wfile.flush()
                        log_frame("TX", resp_header)
                        continue

                    err_bytes = (err or "py_error").encode("utf-8")
                    resp_header = f"{parts[0]}|PY_ARRAY_ERROR|{job_id}|txt|0|{len(err_bytes)}"
                    hb = resp_header.encode("utf-8")
                    frame = b"\xFF" + len(hb).to_bytes(4, "big") + hb + err_bytes
                    self.wfile.write(frame)
                    self.wfile.flush()
                    log_frame("TX", resp_header)
                    continue

                if len(parts) >= 6 and parts[1] == "PY_ARRAY_CALL":
                    name = parts[2]
                    dtype = parts[3]
                    count = int(parts[4])
                    raw_len = int(parts[5])
                    payload = self.rfile.read(raw_len) if raw_len > 0 else b""
                    log_frame("RX", header)
                    log(f"PY_ARRAY_CALL name={name} dtype={dtype} count={count} raw_len={raw_len}")
                    LAST_ARRAY["name"] = name
                    LAST_ARRAY["dtype"] = dtype
                    LAST_ARRAY["count"] = count
                    LAST_ARRAY["data"] = payload
                    resp_header = f"{parts[0]}|PY_ARRAY_RESP|{name}|{dtype}|{count}|{raw_len}"
                    hb = resp_header.encode("utf-8")
                    frame = b"\xFF" + len(hb).to_bytes(4, "big") + hb + payload
                    self.wfile.write(frame)
                    self.wfile.flush()
                    log_frame("TX", resp_header)
                continue

            line = first + self.rfile.readline()
            if not line:
                break

            try:
                log(f"RX PY_CALL json_len={len(line)}")
                req = json.loads(line.decode("utf-8"))
                resp = handle_request(req)
            except Exception as e:
                resp = {"ok": False, "error": str(e)}

            payload = (json.dumps(resp) + "\n").encode("utf-8")
            self.wfile.write(payload)
            self.wfile.flush()


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def run_server():
    with ThreadedTCPServer((HOST, PORT), Handler) as srv:
        log(f"PyOutService escutando em {HOST}:{PORT} (server)")
        srv.serve_forever()


def main():
    if MODE in ("server", "legacy"):
        run_server()
    else:
        log(f"PyOutService gateway mode (hosts={GW_HOSTS} port={GW_PORT})")
        run_gateway_client()


if __name__ == "__main__":
    main()
