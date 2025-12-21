# Camadas e nomes amigáveis (serviço MT5 + Python)

## MT5 (MQL5)
- **OficialTelnetServiceSocket.mq5** (Service) – **escuta TCP em 9090** (modo padrão). Mostra “listening 9090” no Journal quando inicia.
- Suporta `PY_CALL` / `PY_ARRAY_CALL` direto para Python (porta 9100) e frames binários SEND_ARRAY/GET_ARRAY.
- Handlers em `mt5/Services/OficialTelnetServiceSocket/BridgeHandlers.mqh` (MQH em subpasta; MQ5 fica em `mt5/Services/`).
- **OficialTelnetListener.mq5** (Expert, opcional) – modo por arquivos/pipe (não socket).

## Python
- **python/python_bridge_server.py** – “Python‑Bridge”: **server** em 0.0.0.0:9100 (default).
- **python/cmdmt.py** – CLI principal; transporte socket (default 9090) ou file (cmd_/resp_ legado).
- (Legados) **test_socket.py**, **bridge_cli_interativo-mt5.py**, **mt_cli.py** – mantidos, mas o CMD MT substitui.

## Portas padrão (evitar conflito)
- 9090 – Serviço MT5 (padrão).
- 9100 – Python‑Bridge (server).

## Como acoplar outras camadas (HTTP/websocket/pipe)
A lógica de comando fica desacoplada do transporte:
- No serviço MQL, a Dispatch dos comandos está em `MQL5/Services/OficialTelnetServiceSocket/BridgeHandlers.mqh` (camada lógica) e o MQ5 fica em `MQL5/Services/OficialTelnetServiceSocket.mq5`.
- Nos clientes Python, o mapeamento de comandos está no CMD MT; trocar o transporte significa alterar a função de envio/recepção mantendo os mesmos nomes de comandos.

## Nomes amigáveis
- “CMD MT” → python/cmdmt.py (socket 9090) ou file
- “Python‑Bridge” → python/python_bridge_server.py (server default)
- Legados: test_socket.py, bridge_cli_interativo-mt5.py, mt_cli.py

## Handshake / Roteamento
- Conexão direta no serviço (sem HELLO/handshake).
