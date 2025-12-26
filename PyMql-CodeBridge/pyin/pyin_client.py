#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyInClient: cliente externo para PyInServerService (MT5).

Exemplos:
  python pyin_client.py ping --host 127.0.0.1 --port 9091
  python pyin_client.py pycall --json '{"cmd":"ping"}'
  python pyin_client.py array-submit --name foo --seq 16
"""

from __future__ import annotations

import argparse
import socket
import struct
import sys
import time
from typing import Iterable


DTYPE_FMT = {
    "f64": "d",
    "f32": "f",
    "i32": "i",
    "i16": "h",
    "u8": "B",
}


def _req_id() -> str:
    return str(int(time.time() * 1000))


def _build_header(cmd: str, name: str, dtype: str, count: int, raw_len: int) -> str:
    return f"{_req_id()}|{cmd}|{name}|{dtype}|{count}|{raw_len}"


def _parse_values(values: str | None, seq: int | None) -> list[float]:
    if values:
        return [float(v.strip()) for v in values.split(",") if v.strip() != ""]
    if seq is not None:
        return [float(i) for i in range(seq)]
    return []


def _pack_payload(dtype: str, values: Iterable[float]) -> bytes:
    fmt = DTYPE_FMT.get(dtype)
    if not fmt:
        raise ValueError(f"dtype inválido: {dtype}")
    vals = list(values)
    if not vals:
        return b""
    return struct.pack("<" + fmt * len(vals), *vals)


def _send_frame(sock: socket.socket, header: str, payload: bytes) -> None:
    hb = header.encode("utf-8")
    prefix = b"\xFF" + len(hb).to_bytes(4, "big")
    sock.sendall(prefix + hb + payload)


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("socket closed")
        data += chunk
    return data


def _recv_frame(sock: socket.socket) -> tuple[str, bytes]:
    first = _recv_exact(sock, 1)
    if first != b"\xFF":
        rest = sock.recv(4096)
        return (first + rest).decode("utf-8", "ignore"), b""
    header_len = int.from_bytes(_recv_exact(sock, 4), "big")
    header = _recv_exact(sock, header_len).decode("utf-8", "ignore")
    parts = header.split("|")
    raw_len = int(parts[5]) if len(parts) >= 6 else 0
    payload = _recv_exact(sock, raw_len) if raw_len > 0 else b""
    return header, payload


def _send_line(sock: socket.socket, line: str) -> None:
    if not line.endswith("\n"):
        line += "\n"
    sock.sendall(line.encode("utf-8"))


def _recv_line(sock: socket.socket) -> str:
    buf = b""
    while True:
        ch = sock.recv(1)
        if not ch:
            raise ConnectionError("socket closed")
        if ch == b"\n":
            break
        buf += ch
    return buf.decode("utf-8", "ignore")


def _read_response(sock: socket.socket, max_lines: int = 3, timeout: float = 0.4) -> list[str]:
    lines = []
    sock.settimeout(timeout)
    try:
        for _ in range(max_lines):
            lines.append(_recv_line(sock))
    except (socket.timeout, ConnectionError):
        pass
    finally:
        sock.settimeout(None)
    return lines


def _split_hosts(hosts: str) -> list[str]:
    return [h.strip() for h in hosts.replace(";", ",").split(",") if h.strip()]


def _dial(hosts: str, port: int, timeout: float) -> socket.socket:
    last_err = None
    for host in _split_hosts(hosts):
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.settimeout(timeout)
            return sock
        except Exception as e:
            last_err = e
            continue
    if last_err:
        raise last_err
    raise RuntimeError("no_host_available")


def cmd_ping(args: argparse.Namespace) -> int:
    with _dial(args.host, args.port, args.timeout) as sock:
        _send_line(sock, f"{_req_id()}|PING")
        resp = _read_response(sock, max_lines=2, timeout=args.timeout)
        print("\n".join(resp))
    return 0


def cmd_pycall(args: argparse.Namespace) -> int:
    payload = args.json or ""
    with _dial(args.host, args.port, args.timeout) as sock:
        _send_line(sock, f"{_req_id()}|PY_CALL|{payload}")
        resp = _read_response(sock, max_lines=3, timeout=args.timeout)
        print("\n".join(resp))
    return 0


def cmd_raw(args: argparse.Namespace) -> int:
    line = args.line or ""
    with _dial(args.host, args.port, args.timeout) as sock:
        _send_line(sock, line)
        resp = _read_response(sock, max_lines=3, timeout=args.timeout)
        print("\n".join(resp))
    return 0


def cmd_cmd(args: argparse.Namespace) -> int:
    cmd = (args.cmd or "").strip()
    params = args.params or []
    if not cmd:
        raise ValueError("cmd vazio")
    line = "|".join([_req_id(), cmd] + list(params))
    with _dial(args.host, args.port, args.timeout) as sock:
        _send_line(sock, line)
        resp = _read_response(sock, max_lines=3, timeout=args.timeout)
        print("\n".join(resp))
    return 0


def cmd_array_submit(args: argparse.Namespace) -> int:
    values = _parse_values(args.values, args.seq)
    payload = _pack_payload(args.dtype, values)
    header = _build_header("PY_ARRAY_SUBMIT", args.name, args.dtype, len(values), len(payload))
    with _dial(args.host, args.port, args.timeout) as sock:
        _send_frame(sock, header, payload)
        h, _ = _recv_frame(sock)
        print(h)
    return 0


def cmd_array_poll(args: argparse.Namespace) -> int:
    header = f"{_req_id()}|PY_ARRAY_POLL|{args.job}|{args.dtype}|0|0"
    with _dial(args.host, args.port, args.timeout) as sock:
        _send_frame(sock, header, b"")
        h, payload = _recv_frame(sock)
        print(h)
        if payload:
            print(payload.decode("utf-8", "ignore"))
    return 0


def cmd_array_call(args: argparse.Namespace) -> int:
    values = _parse_values(args.values, args.seq)
    payload = _pack_payload(args.dtype, values)
    header = _build_header("PY_ARRAY_CALL", args.name, args.dtype, len(values), len(payload))
    with _dial(args.host, args.port, args.timeout) as sock:
        _send_frame(sock, header, payload)
        h, payload = _recv_frame(sock)
        print(h)
        if payload:
            print(f"payload_len={len(payload)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="PyIn client for PyInServerService (MT5)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=9091)
    p.add_argument("--timeout", type=float, default=3.0)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("ping", help="envia PING")
    sp.set_defaults(fn=cmd_ping)

    sp = sub.add_parser("pycall", help="envia PY_CALL (json/texto)")
    sp.add_argument("--json", required=True)
    sp.set_defaults(fn=cmd_pycall)

    sp = sub.add_parser("raw", help="envia linha raw")
    sp.add_argument("line")
    sp.set_defaults(fn=cmd_raw)

    sp = sub.add_parser("cmd", help="envia id|CMD|p1|p2")
    sp.add_argument("cmd")
    sp.add_argument("params", nargs="*")
    sp.set_defaults(fn=cmd_cmd)

    sp = sub.add_parser("array-submit", help="envia PY_ARRAY_SUBMIT")
    sp.add_argument("--name", required=True)
    sp.add_argument("--dtype", default="f64")
    sp.add_argument("--values")
    sp.add_argument("--seq", type=int)
    sp.set_defaults(fn=cmd_array_submit)

    sp = sub.add_parser("array-poll", help="envia PY_ARRAY_POLL")
    sp.add_argument("--job", required=True)
    sp.add_argument("--dtype", default="f64")
    sp.set_defaults(fn=cmd_array_poll)

    sp = sub.add_parser("array-call", help="envia PY_ARRAY_CALL")
    sp.add_argument("--name", required=True)
    sp.add_argument("--dtype", default="f64")
    sp.add_argument("--values")
    sp.add_argument("--seq", type=int)
    sp.set_defaults(fn=cmd_array_call)

    return p


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
