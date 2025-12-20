"""
Nome amigável: MT5 Service CLI (socket)
Função: cliente de linha de comando para o serviço MQL OficialTelnetServiceSocket

Protocolos:
1) Texto: id|CMD|p1|p2\\n
2) Frame binário (SEND_ARRAY/GET_ARRAY):
   0xFF + 4 bytes (len header, big-endian) + header UTF-8 + raw payload
   header: id|SEND_ARRAY|name|dtype|count|raw_len
   Tipos dtype: f64,f32,i32,i16,u8

Doc completa: docs/PROTOCOL_ARRAY.md
Porta padrão: 9090 (a mesma do serviço MQL)

Comandos rápidos (digitar no prompt):
  ping
  open EURUSD H1
  applytpl EURUSD H1 template.tpl
  closetpl EURUSD H1
  list
  attachind EURUSD H1 IndicatorName 1
  detachind EURUSD H1 IndicatorName 1
  py alguma-coisa   (envia PY_CALL)
  raw 1|PING        (linha bruta já com id|...)
  quit

Camadas: lógica de comando está aqui; transporte é socket TCP. Para acoplar HTTP/websocket,
basta trocar a função send_cmd/recv mantendo o mesmo mapeamento de comandos.
"""

import socket
import sys

# Cliente default para o gateway (porta 9095). Ajuste se quiser falar direto com o serviço MQL 9090.
HOST = "127.0.0.1"
PORT = 9095

def send_cmd(sock, cmd, *params, cid=None):
    cid = cid or str(send_cmd.counter)
    send_cmd.counter += 1
    line = "|".join([cid, cmd] + list(params)) + "\n"
    sock.sendall(line.encode("utf-8"))
    data = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
        if b"\n" in data:
            break
    return data.decode("utf-8", errors="ignore")
send_cmd.counter = 1


def main(host, port):
    print(f"Conectando a {host}:{port} (serviço socket)")
    with socket.create_connection((host, port), timeout=3) as s:
        while True:
            try:
                line = input("svc> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nsaindo...")
                break
            if not line:
                continue
            if line.lower() in ("quit", "exit"):
                break

            # raw: envia linha já com id|...
            if line.lower().startswith("raw "):
                raw = line[4:]
                if not raw.endswith("\n"):
                    raw += "\n"
                s.sendall(raw.encode("utf-8"))
                resp = s.recv(4096).decode("utf-8", errors="ignore")
                print(resp)
                continue

            parts = line.split()
            cmd = parts[0].lower()
            try:
                if cmd == "ping":
                    resp = send_cmd(s, "PING")
                elif cmd == "open" and len(parts)>=3:
                    resp = send_cmd(s, "OPEN_CHART", parts[1], parts[2])
                elif cmd == "applytpl" and len(parts)>=4:
                    resp = send_cmd(s, "APPLY_TPL", parts[1], parts[2], parts[3])
                elif cmd == "closetpl" and len(parts)>=3:
                    resp = send_cmd(s, "CLOSE_CHART", parts[1], parts[2])
                elif cmd == "list":
                    resp = send_cmd(s, "LIST_CHARTS")
                elif cmd == "attachind" and len(parts)>=5:
                    resp = send_cmd(s, "ATTACH_IND_FULL", parts[1], parts[2], parts[3], parts[4])
                elif cmd == "detachind" and len(parts)>=5:
                    resp = send_cmd(s, "DETACH_IND_FULL", parts[1], parts[2], parts[3], parts[4])
                elif cmd == "indtotal" and len(parts)>=3:
                    sub = parts[3] if len(parts)>=4 else "1"
                    resp = send_cmd(s, "IND_TOTAL", parts[1], parts[2], sub)
                elif cmd == "indname" and len(parts)>=4:
                    sub = parts[4] if len(parts)>=5 else "1"
                    resp = send_cmd(s, "IND_NAME", parts[1], parts[2], sub, parts[3])
                elif cmd == "attach_ea" and len(parts)>=4:
                    resp = send_cmd(s, "ATTACH_EA_FULL", parts[1], parts[2], parts[3])
                elif cmd == "runscript" and len(parts)>=4:
                    # RUN_SCRIPT params: SYMBOL TF TEMPLATE (usa ScriptActions)
                    resp = send_cmd(s, "RUN_SCRIPT", parts[1], parts[2], parts[3])
                elif cmd == "py" and len(parts)>=2:
                    payload = " ".join(parts[1:])
                    resp = send_cmd(s, "PY_CALL", payload)
                else:
                    print("comando não reconhecido ou params faltando")
                    continue
            except Exception as e:
                print("erro:", e)
                continue

            print(resp.strip())


if __name__ == "__main__":
    h = sys.argv[1] if len(sys.argv)>=2 else HOST
    p = int(sys.argv[2]) if len(sys.argv)>=3 else PORT
    main(h, p)
