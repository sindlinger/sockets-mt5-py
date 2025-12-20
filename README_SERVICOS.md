# Camadas e nomes amigáveis (serviço MT5 + Python)

## MT5 (MQL5)
- **OficialTelnetServiceSocket.mq5** (Service) – **escuta TCP em 9090** (modo padrão). Mostra “listening 9090” no Journal quando inicia.
- Suporta `PY_CALL` / `PY_ARRAY_CALL` direto para Python (porta 9100) e frames binários SEND_ARRAY/GET_ARRAY.
- **Modo gateway (opcional)**: `InpUseGateway=true` faz o MT5 conectar no gateway (porta 9095). Não é o padrão.
- Handlers em `mt5/Services/OficialTelnetServiceSocket/BridgeHandlers.mqh` (MQH em subpasta; MQ5 fica em `mt5/Services/`).
- **OficialTelnetListener.mq5** (Expert, opcional) – modo por arquivos/pipe (não socket).

## Python
- **python/gateway_server.py** / **python/mt_bridge_server.py** – gateway single‑port (9095) que **proxy** para o MT5 em 9090.
- **python/python_bridge_server.py** – “Python‑Bridge”: **server** em 0.0.0.0:9100 (default). Modo gateway opcional com `PYBRIDGE_MODE=gateway`.
- **cli/cli_unificado.py** – CLI única; transporte socket (default 9095) ou file (cmd_/resp_ legado).
- (Legados) **test_socket.py**, **bridge_cli_interativo-mt5.py**, **mt_cli.py** – mantidos, mas o CLI unificado substitui.

## Portas padrão (evitar conflito)
- 9090 – Serviço MT5 (padrão).
- 9095 – Gateway (proxy para 9090).
- 9100 – Python‑Bridge (server).

## Como acoplar outras camadas (HTTP/websocket/pipe)
A lógica de comando fica desacoplada do transporte:
- No serviço MQL, a Dispatch dos comandos está em `MQL5/Services/OficialTelnetServiceSocket/BridgeHandlers.mqh` (camada lógica) e o MQ5 fica em `MQL5/Services/OficialTelnetServiceSocket.mq5`.
- Nos clientes Python, o mapeamento de comandos está no CLI unificado; trocar o transporte significa alterar a função de envio/recepção mantendo os mesmos nomes de comandos.

## Nomes amigáveis
- “Gateway HUB” → python/gateway_server.py (também python/mt_bridge_server.py) porta 9095
- “CLI Unificado (CMD MT)” → cli/cli_unificado.py (socket 9095 ou file)
- “Python‑Bridge” → python/python_bridge_server.py (gateway mode default)
- Legados: test_socket.py, bridge_cli_interativo-mt5.py, mt_cli.py

## Handshake / Roteamento
- O gateway ignora linhas `HELLO ...` (não responde).  
- Se conectar **direto** ao serviço MT5 (porta 9090) com `cmdmt`, desative o hello: `CMDMT_HELLO=0`.
- Python bridge pode rodar em modo gateway opcional: `PYBRIDGE_MODE=gateway` (não é o padrão).
