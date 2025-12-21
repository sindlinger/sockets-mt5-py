import json
import time
import threading
from collections import defaultdict, deque
import socketserver

HOST = "127.0.0.1"
# Legado: usa serviço direto (9090). Gateway não é usado neste setup.
PORT = 9095

lock = threading.Lock()

# fila de comandos por símbolo
queues = defaultdict(deque)

# último "heartbeat" / último request visto do EA por símbolo
last_seen = {}  # symbol -> dict


def push_cmd(symbol: str, cmd: dict):
    with lock:
        queues[symbol].append(cmd)
        qlen = len(queues[symbol])
    return qlen


def pop_cmd(symbol: str):
    with lock:
        if queues[symbol]:
            return queues[symbol].popleft()
    return None


def set_last_seen(symbol: str, req: dict):
    with lock:
        last_seen[symbol] = {
            "ts": time.time(),
            "symbol": symbol,
            "tf": req.get("tf"),
            "time": req.get("time"),
            "c": req.get("c"),
            "v": req.get("v"),
            "ma_fast": req.get("ma_fast"),
            "ma_slow": req.get("ma_slow"),
            "rsi": req.get("rsi"),
        }


def get_status(symbol: str | None):
    with lock:
        if symbol:
            return last_seen.get(symbol)
        return dict(last_seen)


def handle_json(req: dict) -> dict:
    cmd = req.get("cmd")

    if cmd == "ping":
        return {"ok": True, "pong": True, "ts": time.time()}

    # EA chama isso a cada OnTimer (ou a cada candle)
    if cmd == "signal":
        symbol = req.get("symbol", "UNKNOWN")
        set_last_seen(symbol, req)

        # 1) se tiver comando manual enfileirado, ele tem prioridade
        manual = pop_cmd(symbol)
        if manual:
            manual_resp = {"ok": True, **manual, "source": "manual"}
            return manual_resp

        # 2) senão: default HOLD (você pode plugar FracJax aqui)
        return {"ok": True, "action": "HOLD", "source": "auto"}

    # CLI manda isso
    if cmd == "cli_push":
        symbol = req.get("symbol")
        action = (req.get("action") or "").upper()
        lots = req.get("lots")

        if not symbol:
            return {"ok": False, "error": "faltou symbol"}
        if action not in ("BUY", "SELL", "CLOSE", "HOLD"):
            return {"ok": False, "error": f"action inválida: {action}"}

        payload = {"action": action}
        if lots is not None:
            payload["lots"] = lots

        qlen = push_cmd(symbol, payload)
        return {"ok": True, "queued": qlen, "symbol": symbol, "action": action}

    if cmd == "status":
        symbol = req.get("symbol")
        st = get_status(symbol)
        return {"ok": True, "status": st}

    return {"ok": False, "error": f"cmd desconhecido: {cmd}"}


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        while True:
            line = self.rfile.readline()
            if not line:
                break

            line = line.strip()
            if not line:
                continue

            try:
                req = json.loads(line.decode("utf-8"))
                resp = handle_json(req)
            except Exception as e:
                resp = {"ok": False, "error": str(e)}

            self.wfile.write((json.dumps(resp) + "\n").encode("utf-8"))
            self.wfile.flush()


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    with ThreadedTCPServer((HOST, PORT), Handler) as srv:
        print(f"MT bridge server escutando em {HOST}:{PORT}")
        srv.serve_forever()
