#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Exemplo de uso do protocolo binário SEND_ARRAY / GET_ARRAY.
Requer o serviço MT5 Python-only (OficialTelnetServicePySocket) escutando (porta 9091).
"""

import socket
import struct
import sys


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


def recv_frame(sock: socket.socket) -> tuple[str, bytes]:
    first = recv_exact(sock, 1)
    if first != b"\xFF":
        # fallback: texto
        rest = sock.recv(4096)
        return (first + rest).decode("utf-8", "ignore"), b""
    header_len = int.from_bytes(recv_exact(sock, 4), "big")
    header = recv_exact(sock, header_len).decode("utf-8", "ignore")
    parts = header.split("|")
    if len(parts) >= 6:
        raw_len = int(parts[5])
        raw = recv_exact(sock, raw_len) if raw_len > 0 else b""
        return header, raw
    return header, b""


def send_array(sock: socket.socket, name: str, dtype: str, values: list[float], req_id="1"):
    # dtype suportado: f64,f32,i32,i16,u8
    fmt_map = {"f64": "d", "f32": "f", "i32": "i", "i16": "h", "u8": "B"}
    if dtype not in fmt_map:
        raise ValueError("dtype inválido")
    fmt = "<" + fmt_map[dtype] * len(values)
    payload = struct.pack(fmt, *values)
    header = f"{req_id}|SEND_ARRAY|{name}|{dtype}|{len(values)}|{len(payload)}"
    frame = build_frame(header, payload)
    sock.sendall(frame)
    return sock.recv(4096).decode("utf-8", "ignore")


def get_array(sock: socket.socket, name: str, dtype: str, count: int, req_id="2"):
    fmt_map = {"f64": "d", "f32": "f", "i32": "i", "i16": "h", "u8": "B"}
    if dtype not in fmt_map:
        raise ValueError("dtype inválido")
    raw_len = count * struct.calcsize(fmt_map[dtype])
    header = f"{req_id}|GET_ARRAY|{name}|{dtype}|{count}|{raw_len}"
    frame = build_frame(header)
    sock.sendall(frame)
    header_resp, raw = recv_frame(sock)
    fmt = "<" + fmt_map[dtype] * count
    values = list(struct.unpack(fmt, raw)) if raw else []
    return header_resp, values


def main():
    host = sys.argv[1] if len(sys.argv) >= 2 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) >= 3 else 9091
    with socket.create_connection((host, port), timeout=3) as s:
        print("SEND_ARRAY ->", send_array(s, "prices", "f64", [1.1, 2.2, 3.3]))
        header, values = get_array(s, "prices", "f64", 3)
        print("GET_ARRAY header:", header)
        print("GET_ARRAY values:", values)


if __name__ == "__main__":
    main()
