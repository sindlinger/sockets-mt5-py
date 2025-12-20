#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smoke tests for MT5 socket service (OficialTelnetServiceSocket).
Only runs safe commands by default (no trades). Optional EA/indicator tests
can be enabled via args.
"""

import argparse
import json
import socket
import time


def send_line(host: str, port: int, line: str, timeout: float = 3.0, hello: bool = False) -> str:
    if not line.endswith("\n"):
        line += "\n"
    with socket.create_connection((host, port), timeout=timeout) as s:
        if hello:
            s.sendall(b"HELLO CMDMT\n")
        s.sendall(line.encode("utf-8"))
        data = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break
    return data.decode("utf-8", errors="ignore")


def parse_resp(resp: str):
    # gateway JSON?
    try:
        obj = json.loads(resp.strip())
        if isinstance(obj, dict):
            if "resp" in obj:
                return parse_resp(str(obj.get("resp", "")))
            ok = bool(obj.get("ok", True))
            msg = obj.get("error") or obj.get("msg") or ("ok" if ok else "error")
            return ok, msg, []
    except Exception:
        pass
    txt = resp.replace("\r", "").splitlines()
    status = txt[0].strip() if txt else ""
    msg = txt[1].strip() if len(txt) >= 2 else ""
    data = txt[2:] if len(txt) >= 3 else []
    ok = status == "OK"
    return ok, msg, data


def send_cmd(host, port, cid, cmd, params, timeout, hello=False):
    line = "|".join([str(cid), cmd] + params)
    resp = send_line(host, port, line, timeout=timeout, hello=hello)
    return parse_resp(resp)


def run_test(name, host, port, cid, cmd, params, timeout, hello=False, expect_ok=True):
    ok, msg, data = send_cmd(host, port, cid, cmd, params, timeout, hello=hello)
    status = "OK" if ok else "ERROR"
    print(f"[{name}] {status} {msg}")
    if expect_ok and not ok:
        raise RuntimeError(f"{name} failed: {msg}")
    return ok, msg, data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9090)
    ap.add_argument("--gateway", action="store_true", help="usa handshake HELLO CMDMT + porta gateway")
    ap.add_argument("--timeout", type=float, default=4.0)
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--tf", default="H1")
    ap.add_argument("--window-name", default="")
    ap.add_argument("--snapshot", default="cmdmt_smoke")
    ap.add_argument("--screenshot", default="MQL5\\Files\\cmdmt_smoke.png")
    ap.add_argument("--sweep-folder", default="MQL5\\Files")
    ap.add_argument("--sweep-base", default="cmdmt_sweep")
    ap.add_argument("--sweep-steps", type=int, default=3)
    ap.add_argument("--sweep-shift", type=int, default=50)
    ap.add_argument("--sweep-align", default="left")
    ap.add_argument("--sweep-width", type=int, default=1280)
    ap.add_argument("--sweep-height", type=int, default=720)
    ap.add_argument("--sweep-fmt", default="png")
    ap.add_argument("--sweep-delay", type=int, default=50)
    ap.add_argument("--ea", default="")
    ap.add_argument("--indicator", default="")
    ap.add_argument("--sub", type=int, default=1)
    ap.add_argument("--set-input", default="")  # key=val
    ap.add_argument("--skip-sweep", action="store_true")
    args = ap.parse_args()

    cid = 1

    # Core smoke tests
    run_test("ping", args.host, args.port, cid, "PING", [], args.timeout, hello=args.gateway); cid += 1
    run_test("open_chart", args.host, args.port, cid, "OPEN_CHART", [args.symbol, args.tf], args.timeout, hello=args.gateway); cid += 1
    run_test("list_charts", args.host, args.port, cid, "LIST_CHARTS", [], args.timeout, hello=args.gateway, expect_ok=False); cid += 1
    run_test("redraw", args.host, args.port, cid, "REDRAW_CHART", [args.symbol, args.tf], args.timeout, hello=args.gateway); cid += 1
    run_test("drop_info", args.host, args.port, cid, "DROP_INFO", [], args.timeout, hello=args.gateway); cid += 1

    # Snapshot tests
    run_test("snapshot_save", args.host, args.port, cid, "SNAPSHOT_SAVE", [args.snapshot], args.timeout, hello=args.gateway); cid += 1
    run_test("snapshot_list", args.host, args.port, cid, "SNAPSHOT_LIST", [], args.timeout, hello=args.gateway); cid += 1
    run_test("snapshot_apply", args.host, args.port, cid, "SNAPSHOT_APPLY", [args.snapshot], args.timeout, hello=args.gateway); cid += 1

    # Screenshot (single)
    run_test("screenshot", args.host, args.port, cid, "SCREENSHOT", [args.symbol, args.tf, args.screenshot, "1280", "720"], args.timeout, hello=args.gateway); cid += 1

    # Window find (optional)
    if args.window_name:
        run_test("window_find", args.host, args.port, cid, "WINDOW_FIND", [args.symbol, args.tf, args.window_name], args.timeout, hello=args.gateway); cid += 1

    # Sweep (optional)
    if not args.skip_sweep:
        run_test(
            "screenshot_sweep",
            args.host,
            args.port,
            cid,
            "SCREENSHOT_SWEEP",
            [
                args.symbol,
                args.tf,
                args.sweep_folder,
                args.sweep_base,
                str(args.sweep_steps),
                str(args.sweep_shift),
                args.sweep_align,
                str(args.sweep_width),
                str(args.sweep_height),
                args.sweep_fmt,
                str(args.sweep_delay),
            ],
            args.timeout,
            hello=args.gateway,
        )
        cid += 1

    # Optional EA tests (requires EA or template present)
    if args.ea:
        run_test("attach_ea", args.host, args.port, cid, "ATTACH_EA_FULL", [args.symbol, args.tf, args.ea], args.timeout, hello=args.gateway, expect_ok=False); cid += 1
        run_test("detach_ea", args.host, args.port, cid, "DETACH_EA_FULL", [], args.timeout, hello=args.gateway, expect_ok=False); cid += 1

    # Optional indicator tests
    if args.indicator:
        run_test("attach_ind", args.host, args.port, cid, "ATTACH_IND_FULL", [args.symbol, args.tf, args.indicator, str(args.sub)], args.timeout, hello=args.gateway, expect_ok=False); cid += 1
        run_test("ind_total", args.host, args.port, cid, "IND_TOTAL", [args.symbol, args.tf, str(args.sub)], args.timeout, hello=args.gateway, expect_ok=False); cid += 1

    # Optional inputs tests (requires last attach context)
    if args.set_input:
        if "=" not in args.set_input:
            raise SystemExit("--set-input deve estar no formato key=val")
        key, val = args.set_input.split("=", 1)
        run_test("set_input", args.host, args.port, cid, "SET_INPUT", [key, val], args.timeout, hello=args.gateway, expect_ok=False); cid += 1
        run_test("list_inputs", args.host, args.port, cid, "LIST_INPUTS", [], args.timeout, hello=args.gateway, expect_ok=False); cid += 1

    print("\nSmoke tests finalizados.")


if __name__ == "__main__":
    main()
