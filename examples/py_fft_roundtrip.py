#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
End-to-end FFT via MT5 Python service + Python bridge.

Flow:
  1) SEND_ARRAY -> MT5 Python service (9091)
  2) PY_ARRAY_CALL|fft?... -> MT5 forwards frame to Python bridge (9100)
  3) GET_ARRAY -> receive FFT magnitude array

Notes:
  - FFT is computed on the Python side (cuPy if available, numpy fallback).
  - Requires MT5 service running and PyMql-CodeBridge/pyout/pyout_server.py running.
"""

import argparse
import math
import socket
import struct


def build_frame(header: str, payload: bytes | None = None) -> bytes:
    hb = header.encode("utf-8")
    prefix = b"\xFF" + len(hb).to_bytes(4, "big")
    return prefix + hb + (payload or b"")


def recv_exact(sock: socket.socket, n: int) -> bytes:
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("socket closed")
        data += chunk
    return data


def recv_line(sock: socket.socket) -> str:
    data = b""
    while b"\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    return data.decode("utf-8", "ignore")


def recv_frame(sock: socket.socket) -> tuple[str, bytes]:
    first = recv_exact(sock, 1)
    if first != b"\xFF":
        rest = sock.recv(4096)
        return (first + rest).decode("utf-8", "ignore"), b""
    header_len = int.from_bytes(recv_exact(sock, 4), "big")
    header = recv_exact(sock, header_len).decode("utf-8", "ignore")
    parts = header.split("|")
    raw = b""
    if len(parts) >= 6:
        raw_len = int(parts[5])
        if raw_len > 0:
            raw = recv_exact(sock, raw_len)
    return header, raw


def send_array(sock: socket.socket, name: str, dtype: str, values: list[float], req_id="1") -> str:
    fmt_map = {"f64": "d", "f32": "f", "i32": "i", "i16": "h", "u8": "B"}
    if dtype not in fmt_map:
        raise ValueError("dtype inválido")
    fmt = "<" + fmt_map[dtype] * len(values)
    payload = struct.pack(fmt, *values)
    header = f"{req_id}|SEND_ARRAY|{name}|{dtype}|{len(values)}|{len(payload)}"
    frame = build_frame(header, payload)
    sock.sendall(frame)
    return recv_line(sock).strip()


def get_array(sock: socket.socket, req_id="3") -> tuple[str, list[float]]:
    # GET_ARRAY doesn't require count here; MT5 uses the last stored array.
    header = f"{req_id}|GET_ARRAY"
    frame = build_frame(header)
    sock.sendall(frame)
    header_resp, raw = recv_frame(sock)
    parts = header_resp.split("|")
    if len(parts) < 6:
        return header_resp, []
    dtype = parts[3]
    count = int(parts[4])
    fmt_map = {"f64": "d", "f32": "f", "i32": "i", "i16": "h", "u8": "B"}
    if dtype not in fmt_map or count <= 0 or not raw:
        return header_resp, []
    fmt = "<" + fmt_map[dtype] * count
    values = list(struct.unpack(fmt, raw[: struct.calcsize(fmt)]))
    return header_resp, values


def make_signal(n: int, freq: float, sample_rate: float) -> list[float]:
    out = []
    for i in range(n):
        t = i / sample_rate
        out.append(math.sin(2 * math.pi * freq * t))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9091)
    ap.add_argument("--n", type=int, default=256)
    ap.add_argument("--freq", type=float, default=5.0)
    ap.add_argument("--sample-rate", type=float, default=100.0)
    ap.add_argument("--name", default="fft?half=1&norm=1")
    ap.add_argument("--print", type=int, default=8, dest="print_n")
    args = ap.parse_args()

    values = make_signal(args.n, args.freq, args.sample_rate)
    with socket.create_connection((args.host, args.port), timeout=5) as s:
        print("SEND_ARRAY ->", send_array(s, "signal", "f64", values, req_id="1"))
        line = f"2|PY_ARRAY_CALL|{args.name}\n"
        s.sendall(line.encode("utf-8"))
        print("PY_ARRAY_CALL ->", recv_line(s).strip())
        header, fft_vals = get_array(s, req_id="3")
        print("GET_ARRAY header:", header)
        if fft_vals:
            print("FFT len:", len(fft_vals))
            if args.print_n > 0:
                print("FFT first:", fft_vals[: args.print_n])
        else:
            print("FFT vazio ou erro de parse")


if __name__ == "__main__":
    main()
