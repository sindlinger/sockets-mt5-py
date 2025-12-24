# Camadas e nomes amigáveis (serviço MT5 + Python)

## MT5 (MQL5)
- **OficialTelnetServiceSocket.mq5** (Service) – **escuta TCP em 9090** (modo padrão). Mostra “listening 9090” no Journal quando inicia.
- **Sem PY_***: comandos de Python foram movidos para um serviço dedicado.
- **PyInService.mq5** (**PyInService / pyin**) – **escuta TCP em 9091**. Suporta `PY_CALL` / `PY_ARRAY_CALL` e frames binários `SEND_ARRAY`/`GET_ARRAY` (PyOutService em 9100).
- **OficialTelnetServiceBootstrap.mq5** (Service) – **one‑shot** para disparar **compilação** + **start** de serviços via arquivo em `MQL5/Files`.
- Handlers em `mt5/Services/OficialTelnetServiceSocket/ServiceHandlers.mqh` (MQH em subpasta; MQ5 fica em `mt5/Services/`).
- **OficialTelnetListener.mq5** (Expert, opcional) – modo por arquivos/pipe (não socket).

## Python
- **PyMql-CodeBridge/pyout/pyout_server.py** (**PyOutService / pyout**) – **server** em 0.0.0.0:9100 (default).
- **python/cmdmt.py** – CLI principal; transporte socket (default 9090) ou file (cmd_/resp_ legado).
- **PyMql-CodeBridge/pyout/registry.py** – registry (commands/arrays) do PyOut.
- **PyMql-CodeBridge/pyout/commands.py** – comandos JSON (PY_CALL).
- **PyMql-CodeBridge/pyout/arrays.py** – arrays (PY_ARRAY_CALL).
  - wrappers legacy: `python/python_bridge_server.py` e `python/mt5_bridge.py`
- **scripts/mt5_bootstrap_agent.py** – agent que observa `bootstrap_request.txt`, compila e inicia serviços (UI).
- (Legados) **test_socket.py**, **bridge_cli_interativo-mt5.py**, **mt_cli.py** – mantidos, mas o CMD MT substitui.

## Portas padrão (evitar conflito)
- 9090 – Serviço MT5 (padrão).
- 9091 – Serviço MT5 Python‑only.
- 9100 – Python‑Bridge (server).

## Como acoplar outras camadas (HTTP/websocket/pipe)
A lógica de comando fica desacoplada do transporte:
- No serviço MQL, a Dispatch dos comandos está em `MQL5/Services/OficialTelnetServiceSocket/BridgeHandlers.mqh` (camada lógica) e o MQ5 fica em `MQL5/Services/OficialTelnetServiceSocket.mq5`.
- Nos clientes Python, o mapeamento de comandos está no CMD MT; trocar o transporte significa alterar a função de envio/recepção mantendo os mesmos nomes de comandos.

## Nomes amigáveis
- “CMD MT” → python/cmdmt.py (socket 9090) ou file
- “PyOutService / pyout” → PyMql-CodeBridge/pyout/pyout_server.py (server default)
- “PyBridge SDK” → mt5/Services/PyInService/PyInBridge.mqh + PyMql-CodeBridge/pyout/registry.py

## Mini‑SDK (facilitar MQL↔Python)
- **MQL**: `mt5/Services/PyInService/PyInBridge.mqh` (PyInService / pyin)
  - `PyBridgeCalcF64(...)` envia array → PY_ARRAY_CALL → GET_ARRAY (resultado pronto).
- **Python**: `PyMql-CodeBridge/pyout/registry.py`
  - registre novos comandos e arrays via `REGISTRY.add_cmd()` / `REGISTRY.add_array()`.

## Referências
- Modelo de execução do MQL5: `docs/MQL5_RUNTIME_MODEL.md`
- Bootstrap (legacy): `../lixeira/legacy-sockets-python/PyMql-CodeBridge/integrations/python-mql/notes/MT5_BOOTSTRAP_SERVICE.md`
- Legados: test_socket.py, bridge_cli_interativo-mt5.py, mt_cli.py

## Handshake / Roteamento
- Conexão direta no serviço (sem HELLO/handshake).
