"""Conexão TCP simples com o serviço MQL (OficialTelnetServiceSocket).
Responsabilidade: enviar linha texto (id|CMD|...) e ler primeira linha de resposta.
Com fallback de host (docker-internal -> localhost).
"""

import socket
import os

HOST_MQL = os.environ.get("MT5_HOST", "host.docker.internal")
HOSTS_MQL = os.environ.get("MT5_HOSTS", "host.docker.internal,127.0.0.1")
PORT_MQL = 9090


def _hosts_list(host: str | None):
    if host:
        return [h.strip() for h in host.replace(";", ",").split(",") if h.strip()]
    return [h.strip() for h in HOSTS_MQL.replace(";", ",").split(",") if h.strip()]


def send_line(line: str, host=HOST_MQL, port=PORT_MQL, timeout=2.0) -> tuple[bool, str]:
    last_err = None
    for h in _hosts_list(host):
        try:
            with socket.create_connection((h, port), timeout=timeout) as s:
                if not line.endswith("\n"):
                    line += "\n"
                s.sendall(line.encode("utf-8"))
                resp = b""
                while True:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    resp += chunk
                    if b"\n" in resp:
                        break
                return True, resp.decode("utf-8", errors="ignore")
        except Exception as e:
            last_err = e
    return False, str(last_err) if last_err else "no_host"
