#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Python bridge para MT5.
Modo default: conecta no Gateway (porta única) e responde PY_CALL / PY_ARRAY_CALL.
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
import time

MODE = os.environ.get("PYBRIDGE_MODE", "gateway").lower()
HOST = os.environ.get("PYBRIDGE_HOST", "0.0.0.0")
PORT = int(os.environ.get("PYBRIDGE_PORT", "9100"))
GW_HOSTS = os.environ.get("GW_HOSTS", "host.docker.internal,127.0.0.1")
GW_PORT = int(os.environ.get("GW_PORT", "9095"))

# armazena último array recebido
LAST_ARRAY = {"name": "", "dtype": "", "count": 0, "data": b""}


def handle_request(req: dict) -> dict:
    cmd = req.get("cmd")

    if cmd == "ping":
        return {"ok": True, "pong": True, "ts": time.time()}

    if cmd == "echo":
        return {"ok": True, "data": req.get("data")}

    if cmd == "signal":
        ma_fast = float(req.get("ma_fast", 0.0))
        ma_slow = float(req.get("ma_slow", 0.0))
        rsi     = float(req.get("rsi", 50.0))

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

    return {"ok": False, "error": f"cmd desconhecido: {cmd}"}


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


def handle_frame(frame: bytes, header_text: str) -> bytes:
    parts = header_text.split("|")
    if len(parts) >= 6 and parts[1] == "PY_ARRAY_CALL":
        name = parts[2]
        dtype = parts[3]
        count = int(parts[4])
        raw_len = int(parts[5])
        payload = b""
        if raw_len > 0:
            payload = frame[-raw_len:]
        LAST_ARRAY["name"] = name
        LAST_ARRAY["dtype"] = dtype
        LAST_ARRAY["count"] = count
        LAST_ARRAY["data"] = payload
        # ecoa o mesmo array
        resp_header = f"{parts[0]}|PY_ARRAY_RESP|{name}|{dtype}|{count}|{raw_len}"
        hb = resp_header.encode("utf-8")
        return b"\xFF" + len(hb).to_bytes(4, "big") + hb + payload
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
                if len(parts) >= 6 and parts[1] == "PY_ARRAY_CALL":
                    name = parts[2]
                    dtype = parts[3]
                    count = int(parts[4])
                    raw_len = int(parts[5])
                    payload = self.rfile.read(raw_len) if raw_len > 0 else b""
                    LAST_ARRAY["name"] = name
                    LAST_ARRAY["dtype"] = dtype
                    LAST_ARRAY["count"] = count
                    LAST_ARRAY["data"] = payload
                    resp_header = f"{parts[0]}|PY_ARRAY_RESP|{name}|{dtype}|{count}|{raw_len}"
                    hb = resp_header.encode("utf-8")
                    frame = b"\xFF" + len(hb).to_bytes(4, "big") + hb + payload
                    self.wfile.write(frame)
                    self.wfile.flush()
                continue

            line = first + self.rfile.readline()
            if not line:
                break

            try:
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
        print(f"Python bridge escutando em {HOST}:{PORT} (server)")
        srv.serve_forever()


if __name__ == "__main__":
    if MODE in ("server", "legacy"):
        run_server()
    else:
        run_gateway_client()
