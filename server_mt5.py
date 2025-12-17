import json
import socketserver
import time

HOST = "127.0.0.1"
PORT = 9090

def handle_request(req: dict) -> dict:
    cmd = req.get("cmd")

    if cmd == "ping":
        return {"ok": True, "pong": True, "ts": time.time()}

    if cmd == "echo":
        return {"ok": True, "data": req.get("data")}

    if cmd == "signal":
        # Exemplo simples (você troca pela sua lógica/FracJax depois):
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


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        # rfile/wfile já são "file-like" em cima do socket
        while True:
            line = self.rfile.readline()  # lê até \n
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


if __name__ == "__main__":
    with ThreadedTCPServer((HOST, PORT), Handler) as srv:
        print(f"Python server escutando em {HOST}:{PORT}")
        srv.serve_forever()
