# Camadas e nomes amigáveis (serviço MT5 + Python)

## MT5 (MQL5)
- **OficialTelnetServiceSocket.mq5** (Service) – modo **Gateway** (default): conecta no HUB em `GW_PORT` (9095), envia `HELLO MT5`, recebe comandos e responde com terminador `__END__`. Modo servidor direto (9090) é opcional via `InpUseGateway=false`.
- Suporta `PY_CALL` / `PY_ARRAY_CALL` via gateway (prefixo `PY|` para payload texto) e frames binários SEND_ARRAY/GET_ARRAY.
- Handlers em `mt5/Services/OficialTelnetServiceSocket/BridgeHandlers.mqh` (MQH em subpasta; MQ5 fica em `mt5/Services/`).
- **OficialTelnetListener.mq5** (Expert, opcional) – modo por arquivos/pipe (não socket).

## Python
- **python/gateway_server.py** / **python/mt_bridge_server.py** – HUB único (porta 9095) com handshake `HELLO CMDMT/MT5/PY` e roteamento:
  - CMDMT → MT5 (comandos MQL)
  - MT5 → PY (PY_CALL / PY_ARRAY_CALL)
  - PY → MT5 (respostas)
- **python/python_bridge_server.py** – “Python‑Bridge”: modo default conecta no gateway (HELLO PY). Modo legado: servidor 0.0.0.0:9100.
- **cli/cli_unificado.py** – CLI única; transporte socket (default 9095) ou file (cmd_/resp_ legado).
- (Legados) **test_socket.py**, **bridge_cli_interativo-mt5.py**, **mt_cli.py** – mantidos, mas o CLI unificado substitui.

## Portas padrão (evitar conflito)
- 9095 – Gateway HUB (porta única para CMDMT/MT5/PY).
- 9090 – Serviço MT5 (legado, se InpUseGateway=false).
- 9100 – Python‑Bridge (legado, se PYBRIDGE_MODE=server).

## Como acoplar outras camadas (HTTP/websocket/pipe)
A lógica de comando fica desacoplada do transporte:
- No serviço MQL, a Dispatch dos comandos está em `MQL5/Services/OficialTelnetServiceSocket/BridgeHandlers.mqh` (camada lógica) e o transporte é socket (OficialTelnetServiceSocket) ou pipe (OficialTelnetListener).
- Nos clientes Python, o mapeamento de comandos está no CLI unificado; trocar o transporte significa alterar a função de envio/recepção mantendo os mesmos nomes de comandos.

## Nomes amigáveis
- “Gateway HUB” → python/gateway_server.py (também python/mt_bridge_server.py) porta 9095
- “CLI Unificado (CMD MT)” → cli/cli_unificado.py (socket 9095 ou file)
- “Python‑Bridge” → python/python_bridge_server.py (gateway mode default)
- Legados: test_socket.py, bridge_cli_interativo-mt5.py, mt_cli.py

## Handshake / Roteamento
- Todo cliente que conecta no HUB envia uma linha de hello:
  - `HELLO CMDMT`, `HELLO MT5`, `HELLO PY`
- MT5 responde comandos com terminador `__END__` (config `InpGatewayTerm`).
- Para PY_CALL via gateway, MT5 envia a linha `PY|<payload>` e o HUB encaminha ao Python.
- Se conectar **direto** ao serviço MT5 (porta 9090) com `cmdmt`, desative o hello: `CMDMT_HELLO=0`.
- Python bridge pode rodar em modo gateway (default) ou modo servidor: `PYBRIDGE_MODE=server`.
