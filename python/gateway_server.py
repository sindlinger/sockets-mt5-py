#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gateway HUB (porta única) com handshake de role:
  - HELLO CMDMT
  - HELLO MT5
  - HELLO PY

Roteamento:
  CMDMT -> MT5 (comandos MQL, texto ou frame)
  MT5   -> CMDMT (respostas terminadas por __END__)
  MT5   -> PY    (linhas prefixadas por "PY|" ou frames PY_ARRAY_CALL)
  PY    -> MT5   (respostas PY_CALL/PY_ARRAY_RESP)

Observações:
  - MT5 precisa enviar respostas com terminador __END__ (modo gateway)
  - PY_CALL usa prefixo "PY|" para o gateway encaminhar o payload ao Python
"""

import json
import os
import socket
import socketserver
import threading
import time
from collections import defaultdict, deque

# ---------------- Config ----------------
HOST = os.environ.get("GW_HOST", "0.0.0.0")
PORT = int(os.environ.get("GW_PORT", "9095"))
RESP_TERM = os.environ.get("GW_MT5_TERM", "__END__")

MAX_QUEUE_PER_SYMBOL = 50

# ---------------- Estado local (fila) ----------------
lock = threading.Lock()
queues = defaultdict(deque)   # symbol -> deque de comandos
last_seen = {}                # symbol -> dict com info do EA

# Adaptador de ondas (opcional)
try:
    import ew_adapter
except Exception:
    ew_adapter = None


def _qsize(symbol: str) -> int:
    return len(queues[symbol])


def push_cmd(symbol: str, payload: dict) -> dict:
    symbol = symbol.upper()
    with lock:
        if len(queues[symbol]) >= MAX_QUEUE_PER_SYMBOL:
            return {"ok": False, "error": f"fila cheia para {symbol} (max={MAX_QUEUE_PER_SYMBOL})"}
        queues[symbol].append(payload)
        return {"ok": True, "queued": len(queues[symbol]), "symbol": symbol, **payload}


def pop_cmd(symbol: str):
    symbol = symbol.upper()
    with lock:
        if queues[symbol]:
            return queues[symbol].popleft()
    return None


def clear_queue(symbol: str) -> dict:
    symbol = symbol.upper()
    with lock:
        n = len(queues[symbol])
        queues[symbol].clear()
    return {"ok": True, "cleared": n, "symbol": symbol}


def set_last_seen(symbol: str, req: dict):
    symbol = symbol.upper()
    with lock:
        last_seen[symbol] = {
            "ts": time.time(),
            "symbol": symbol,
            "tf": req.get("tf"),
            "time": req.get("time"),
            "bid": req.get("bid"),
            "ask": req.get("ask"),
            "equity": req.get("equity"),
            "free_margin": req.get("free_margin"),
            "pos": req.get("pos"),
        }


def parse_kv(tokens):
    out = {}
    for t in tokens:
        if "=" in t:
            k, v = t.split("=", 1)
            out[k.strip().lower()] = v.strip()
    return out


def parse_text_command(line: str) -> dict:
    """
    Comandos telnet curtos:
      buy|sell SYMBOL LOTS [sl=pts] [tp=pts]
      close SYMBOL
      hold SYMBOL
      queue SYMBOL
      cancel SYMBOL
      status [SYMBOL]
      ping
      (qualquer linha com '|') -> proxy MQL
    """
    parts = line.strip().split()
    if not parts:
        return {"ok": False, "error": "linha vazia"}

    # Proxy direto se já tem '|'
    if "|" in line:
        return {"proxy_mql": line}

    cmd = parts[0].lower()

    if cmd == "help":
        return {"ok": True, "help": [
            "buy BTCUSD 0.01 sl=500 tp=1000",
            "sell BTCUSD 0.01 sl=500 tp=1000",
            "close BTCUSD",
            "hold BTCUSD",
            "queue BTCUSD",
            "cancel BTCUSD",
            "status [BTCUSD]",
            "ping",
        ]}

    if cmd == "ping":
        return {"ok": True, "pong": True, "ts": time.time()}

    if cmd in ("buy", "sell"):
        if len(parts) < 3:
            return {"ok": False, "error": "use: buy|sell SYMBOL LOTS [sl=PTS] [tp=PTS]"}
        symbol = parts[1].upper()
        lots = float(parts[2])
        kv = parse_kv(parts[3:])
        payload = {"action": cmd.upper(), "lots": lots}
        if "sl" in kv:
            payload["sl_points"] = int(float(kv["sl"]))
        if "tp" in kv:
            payload["tp_points"] = int(float(kv["tp"]))
        return push_cmd(symbol, payload)

    if cmd in ("close", "hold"):
        if len(parts) < 2:
            return {"ok": False, "error": "use: close|hold SYMBOL"}
        symbol = parts[1].upper()
        return push_cmd(symbol, {"action": cmd.upper()})

    if cmd == "queue":
        if len(parts) < 2:
            return {"ok": False, "error": "use: queue SYMBOL"}
        symbol = parts[1].upper()
        with lock:
            return {"ok": True, "symbol": symbol, "queued": _qsize(symbol)}

    if cmd in ("cancel", "clear"):
        if len(parts) < 2:
            return {"ok": False, "error": "use: cancel SYMBOL"}
        return clear_queue(parts[1])

    if cmd == "status":
        symbol = parts[1].upper() if len(parts) >= 2 else None
        with lock:
            if symbol:
                return {"ok": True, "status": last_seen.get(symbol), "queued": _qsize(symbol)}
            summary = {}
            for sym, st in last_seen.items():
                summary[sym] = {"ts": st.get("ts"), "tf": st.get("tf"), "time": st.get("time")}
            q = {sym: len(q) for sym, q in queues.items() if len(q) > 0}
            return {"ok": True, "status": summary, "queues": q}

    return {"ok": False, "error": f"comando desconhecido: {cmd}"}


def handle_json(req: dict) -> dict:
    cmd = req.get("cmd")

    if cmd == "ping":
        return {"ok": True, "pong": True, "ts": time.time()}

    if cmd == "echo":
        return {"ok": True, "data": req.get("data")}

    if cmd in ("ew_analyze", "EW_ANALYZE"):
        if ew_adapter is None:
            return {"ok": False, "error": "ew_adapter não importado"}
        try:
            bars = req.get("bars") or []
            params = req.get("params") or {}
            res = ew_adapter.analyze(bars, params)
            return {"ok": True, "waves": res.get("waves", []), "summary": res.get("summary", {})}
        except Exception as e:
            return {"ok": False, "error": f"ew_analyze fail: {e}"}

    if cmd == "signal":
        symbol = (req.get("symbol") or "UNKNOWN").upper()
        set_last_seen(symbol, req)
        manual = pop_cmd(symbol)
        if manual:
            return {"ok": True, **manual, "source": "manual"}
        return {"ok": True, "action": "HOLD", "source": "auto"}

    if cmd == "mql_raw":
        line = (req.get("line") or "").strip()
        if not line:
            return {"ok": False, "error": "faltou line"}
        return {"proxy_mql": line}

    return {"ok": False, "error": f"cmd desconhecido: {cmd}"}


# ---------------- HUB ----------------
class Conn:
    def __init__(self, sock: socket.socket, addr):
        self.sock = sock
        self.addr = addr
        self.role = None
        self.lock = threading.Lock()
        self.buf = b""

    def send_bytes(self, data: bytes):
        with self.lock:
            self.sock.sendall(data)

    def send_line(self, line: str):
        if not line.endswith("\n"):
            line += "\n"
        self.send_bytes(line.encode("utf-8"))

    def recv_more(self):
        chunk = self.sock.recv(4096)
        if not chunk:
            return False
        self.buf += chunk
        return True


class HubState:
    def __init__(self):
        self.lock = threading.Lock()
        self.mt5 = None
        self.py = None
        self.cmdmt = set()
        self.pending = deque()  # fila de conexões CMDMT aguardando resposta
        self.mt5_resp_lines = []
        self.mt5_outbox = deque()  # (kind, data, conn)
        self.py_inflight = False

    def set_role(self, conn: Conn, role: str):
        with self.lock:
            role = role.upper()
            conn.role = role
            if role == "MT5":
                if self.mt5 and self.mt5 is not conn:
                    try:
                        self.mt5.sock.close()
                    except Exception:
                        pass
                self.mt5 = conn
                self.mt5_resp_lines = []
                self.py_inflight = False
            elif role == "PY":
                if self.py and self.py is not conn:
                    try:
                        self.py.sock.close()
                    except Exception:
                        pass
                self.py = conn
            else:
                self.cmdmt.add(conn)

    def drop_conn(self, conn: Conn):
        with self.lock:
            if conn in self.cmdmt:
                self.cmdmt.discard(conn)
                self.pending = deque([c for c in self.pending if c is not conn])
            if self.mt5 is conn:
                self.mt5 = None
                self.mt5_resp_lines = []
                self.py_inflight = False
            if self.py is conn:
                self.py = None

    def get_mt5(self):
        with self.lock:
            return self.mt5

    def get_py(self):
        with self.lock:
            return self.py

    def enqueue_pending(self, conn: Conn):
        with self.lock:
            self.pending.append(conn)

    def pop_pending(self):
        with self.lock:
            if self.pending:
                return self.pending.popleft()
        return None

    def enqueue_mt5_outbox(self, kind: str, data, conn: Conn):
        with self.lock:
            self.mt5_outbox.append((kind, data, conn))

    def flush_mt5_outbox(self):
        with self.lock:
            items = list(self.mt5_outbox)
            self.mt5_outbox.clear()
        return items


STATE = HubState()


# ---------------- IO helpers ----------------
def read_message(conn: Conn):
    # garante 1 byte no buffer
    if not conn.buf:
        if not conn.recv_more():
            return None

    if conn.buf[0] == 0xFF:
        # precisa de 5 bytes (0xFF + 4 len)
        while len(conn.buf) < 5:
            if not conn.recv_more():
                return None
        hdr_len = int.from_bytes(conn.buf[1:5], "big")
        total = 5 + hdr_len
        while len(conn.buf) < total:
            if not conn.recv_more():
                return None
        header = conn.buf[5:5 + hdr_len]
        header_text = header.decode("utf-8", "ignore")
        # tenta descobrir raw_len
        raw_len = 0
        try:
            parts = header_text.split("|")
            if len(parts) >= 6:
                raw_len = int(parts[5])
        except Exception:
            raw_len = 0
        total = 5 + hdr_len + raw_len
        while len(conn.buf) < total:
            if not conn.recv_more():
                return None
        frame = conn.buf[:total]
        conn.buf = conn.buf[total:]
        return ("frame", frame, header_text)

    # linha
    while b"\n" not in conn.buf:
        if not conn.recv_more():
            if not conn.buf:
                return None
            line_bytes = conn.buf
            conn.buf = b""
            return ("line", line_bytes.decode("utf-8", "replace"), None)
    idx = conn.buf.find(b"\n")
    line_bytes = conn.buf[:idx]
    conn.buf = conn.buf[idx + 1:]
    return ("line", line_bytes.decode("utf-8", "replace"), None)


def is_handshake(line: str):
    return line.strip().upper().startswith("HELLO ")


def parse_role(line: str) -> str:
    parts = line.strip().split()
    return parts[1] if len(parts) >= 2 else ""


def send_json(conn: Conn, obj: dict):
    conn.send_line(json.dumps(obj))


def parse_resp_ok(resp_txt: str) -> bool:
    txt = resp_txt.strip().splitlines()
    if not txt:
        return False
    return txt[0].strip().upper() == "OK"


def send_resp_to_cmdmt(conn: Conn, resp_txt: str):
    ok = parse_resp_ok(resp_txt)
    send_json(conn, {"ok": ok, "resp": resp_txt})


# ---------------- Roteamento ----------------
def forward_to_mt5(kind: str, data, src_conn: Conn):
    mt5 = STATE.get_mt5()
    if not mt5:
        send_json(src_conn, {"ok": False, "error": "mt5_not_connected"})
        return

    if STATE.py_inflight:
        STATE.enqueue_mt5_outbox(kind, data, src_conn)
        return

    if kind == "line":
        line = data
        if not line.endswith("\n"):
            line += "\n"
        mt5.send_bytes(line.encode("utf-8"))
    else:
        mt5.send_bytes(data)

    STATE.enqueue_pending(src_conn)


def route_mt5_response(resp_lines):
    resp_txt = "\n".join(resp_lines).strip()
    if not resp_txt:
        return
    target = STATE.pop_pending()
    if target:
        send_resp_to_cmdmt(target, resp_txt)


def forward_frame_to_py(frame: bytes, header_text: str, mt5_conn: Conn):
    py = STATE.get_py()
    if not py:
        # devolve erro em frame (causa PY_ARRAY_CALL falhar)
        parts = header_text.split("|") if header_text else []
        rid = parts[0] if parts else "0"
        err_header = f"{rid}|PY_ARRAY_ERR"
        hb = err_header.encode("utf-8")
        out = b"\xFF" + len(hb).to_bytes(4, "big") + hb
        mt5_conn.send_bytes(out)
        return
    STATE.py_inflight = True
    py.send_bytes(frame)


def forward_line_to_py(line: str, mt5_conn: Conn):
    py = STATE.get_py()
    if not py:
        err = json.dumps({"ok": False, "error": "py_not_connected"})
        mt5_conn.send_line(err)
        return
    STATE.py_inflight = True
    py.send_line(line)


def handle_cmdmt_message(conn: Conn, msg):
    kind, payload, _ = msg
    if kind == "frame":
        forward_to_mt5("frame", payload, conn)
        return

    line = payload.strip()
    if not line:
        return

    # JSON?
    if line.startswith("{"):
        try:
            req = json.loads(line)
        except Exception:
            req = None
        if isinstance(req, dict):
            resp = handle_json(req)
            if isinstance(resp, dict) and resp.get("proxy_mql"):
                forward_to_mt5("line", resp.get("proxy_mql", ""), conn)
            else:
                send_json(conn, resp)
            return

    # texto comum
    resp = parse_text_command(line)
    if isinstance(resp, dict) and resp.get("proxy_mql"):
        forward_to_mt5("line", resp.get("proxy_mql", ""), conn)
    else:
        send_json(conn, resp)


def handle_mt5_message(conn: Conn, msg):
    kind, payload, header = msg

    if kind == "frame":
        parts = header.split("|") if header else []
        htype = parts[1] if len(parts) >= 2 else ""
        if htype.startswith("PY_"):
            forward_frame_to_py(payload, header or "", conn)
            return
        # resposta CMDMT (frame)
        target = STATE.pop_pending()
        if target:
            target.send_bytes(payload)
        return

    line = payload.rstrip("\r")
    if not line:
        return

    if line.startswith("PY|"):
        forward_line_to_py(line[3:], conn)
        return

    if line == RESP_TERM:
        if STATE.mt5_resp_lines:
            route_mt5_response(STATE.mt5_resp_lines)
        STATE.mt5_resp_lines = []
        return

    STATE.mt5_resp_lines.append(line)


def handle_py_message(conn: Conn, msg):
    kind, payload, header = msg
    mt5 = STATE.get_mt5()
    if not mt5:
        return
    if kind == "frame":
        mt5.send_bytes(payload)
    else:
        mt5.send_line(payload)
    STATE.py_inflight = False
    for kind2, data2, src_conn in STATE.flush_mt5_outbox():
        forward_to_mt5(kind2, data2, src_conn)


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        conn = Conn(self.request, self.client_address)
        while True:
            msg = read_message(conn)
            if not msg:
                break
            kind, payload, header = msg
            if kind == "line" and is_handshake(payload):
                role = parse_role(payload)
                if role:
                    STATE.set_role(conn, role)
                continue
            if conn.role is None:
                STATE.set_role(conn, "CMDMT")
            if conn.role == "MT5":
                handle_mt5_message(conn, msg)
            elif conn.role == "PY":
                handle_py_message(conn, msg)
            else:
                handle_cmdmt_message(conn, msg)

        STATE.drop_conn(conn)
        try:
            conn.sock.close()
        except Exception:
            pass


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    with ThreadedTCPServer((HOST, PORT), Handler) as srv:
        print(f"Gateway HUB escutando em {HOST}:{PORT}")
        srv.serve_forever()


if __name__ == "__main__":
    main()
