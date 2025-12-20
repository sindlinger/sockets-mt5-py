import json
import socket
import sys

BLUE_BG = "\033[44m"
WHITE   = "\033[97m"
RESET   = "\033[0m"

def set_blue():
    sys.stdout.write(BLUE_BG + WHITE)
    sys.stdout.flush()

def reset_color():
    sys.stdout.write(RESET)
    sys.stdout.flush()

def send_line(host, port, line: str):
    with socket.create_connection((host, port), timeout=2) as s:
        s.sendall((line.strip() + "\n").encode("utf-8"))
        data = b""
        while not data.endswith(b"\n"):
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
        if not data:
            return None
        return json.loads(data.decode("utf-8"))

def main():
    host = sys.argv[1] if len(sys.argv) >= 2 else "127.0.0.1"
    # CLI JSON -> gateway; default 9095
    port = int(sys.argv[2]) if len(sys.argv) >= 3 else 9095

    set_blue()
    print("MT5 CLI externo (tipo telnet). Digite help.")
    print(f"Conectando em {host}:{port}")
    print("Exemplos: buy BTCUSD 0.01 | sell BTCUSD 0.01 sl=500 tp=1000 | close BTCUSD | status BTCUSD | quit")
    print("EW analyze: ew caminho_para_barras.json [pivot_lookback] [min_move]")

    while True:
        try:
            line = input("mt> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nsaindo...")
            break

        if not line:
            continue
        if line.lower() in ("quit", "exit"):
            break

        # atalho: 'ew file.json 3 0.0005'
        if line.lower().startswith("ew "):
            parts = line.split()
            if len(parts) < 2:
                print({"ok": False, "error": "uso: ew file.json [pivot_lookback] [min_move]"})
                continue
            fname = parts[1]
            try:
                with open(fname, "r", encoding="utf-8") as f:
                    bars = json.load(f)
            except Exception as e:
                print({"ok": False, "error": f"falha lendo {fname}: {e}"})
                continue

            lb = 3
            mm = 0.0
            if len(parts) >= 3:
                try: lb = int(parts[2])
                except: pass
            if len(parts) >= 4:
                try: mm = float(parts[3])
                except: pass

            payload = {"cmd": "ew_analyze", "bars": bars, "params": {"pivot_lookback": lb, "min_move": mm}}
            try:
                resp = send_line(host, port, json.dumps(payload))
                print(resp)
            except Exception as e:
                print({"ok": False, "error": str(e)})
            continue

        try:
            resp = send_line(host, port, line)
            print(resp)
        except Exception as e:
            print({"ok": False, "error": str(e)})

    reset_color()

if __name__ == "__main__":
    main()
