PyMql-CodeBridge
=================

Objetivo
--------
Bridge simples entre MQL5 (MT5) e Python, com dois canais:
- PyInService (no MT5) recebe comandos e frames binarios do cliente externo.
- PyOutService (pyout/pyout_server.py) processa PY_CALL / PY_ARRAY_CALL.

Arvore (PyOut)
--------------
PyMql-CodeBridge/
  README.md
  PROTOCOL.md
  CMDMT.md
  pyout/
    pyout_server.py
    registry.py
    commands.py
    arrays.py

Arquitetura
-----------

[Python externo (cliente)]  ->  [MT5 PyInService :9091]  ->  [PyOutService :9100]

- O cliente externo conecta SOMENTE no PyIn (porta 9091).
- O PyIn abre conexao exclusiva com o PyOut (porta 9100) quando precisa calcular.
- O PyOut roda fora do MT5 (Windows ou WSL) e responde com JSON/arrays.

Componentes
-----------
- MT5 service (PyIn):
  - arquivo: mt5/Services/PyInService.mq5
  - header/bridge: mt5/Services/PyInService/PyInBridge.mqh
- Python bridge (PyOut):
  - PyMql-CodeBridge/pyout/pyout_server.py
  - registry: PyMql-CodeBridge/pyout/registry.py
  - commands: PyMql-CodeBridge/pyout/commands.py
  - arrays: PyMql-CodeBridge/pyout/arrays.py
  - wrappers legacy: python/legado/python_bridge_server.py + python/legado/mt5_bridge.py

Protocolos
----------
- Texto (linha): id|CMD|p1|p2\n
  Ex:
    1|PING\n
    2|PY_CALL|{"cmd":"ping"}\n
- Frame binario (arrays):
  0xFF + 4 bytes (header_len big-endian) + header UTF-8 + payload
  Header:
    id|SEND_ARRAY|name|dtype|count|raw_len
    id|GET_ARRAY|name|dtype|count|raw_len

Fluxo de array (via PyIn)
-------------------------
1) Client -> PyIn: SEND_ARRAY (frame binario)
2) Client -> PyIn: PY_ARRAY_CALL|nome (linha)
3) PyIn -> PyOut: PY_ARRAY_CALL (frame binario)
4) PyOut -> PyIn: PY_ARRAY_RESP (frame binario)
5) Client -> PyIn: GET_ARRAY (frame binario)

CLI (cmdmt)
-----------
Todos os comandos Python ficam sob o namespace "python" (ou "py"):

- python service <ping|cmd|raw|compile> [args...]
- python bridge <start|stop|status|ping|ensure> [host] [port]
- python build -i stfft [NOME] [--buffers N]

Exemplo (scaffold STFFT):
  cmdmt python build -i stfft MeuIndicador --buffers 2

Detalhes do papel do cmdmt:
  veja PyMql-CodeBridge/CMDMT.md

Nota sobre buffers
------------------
--buffers define QUANTOS BUFFERS sao desenhados no indicador.
Nao define quantos arrays existem no protocolo.

Legado
------
Somente a documentacao antiga da integracao Python foi movida para:
  ../lixeira/legacy-sockets-python/PyMql-CodeBridge/integrations/python-mql/
