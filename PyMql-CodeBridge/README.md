PyMql-CodeBridge
=================

Objetivo
--------
Bridge simples entre MQL5 (MT5) e Python, com quatro papéis:
- PyInServerService (MT5) recebe comandos do cliente Python.
- PyInClient (Python) conecta no PyInServer (testes/controle).
- PyOutService (pyout/pyout_server.py) processa PY_CALL / PY_ARRAY_*.
- PyOutClient (MQL5/indicador) conecta direto no PyOutServer.

Variante CuPy (GPU)
-------------------
- PyInCupyServiceBridge (MT5) faz bridge entre indicador e PyOut CuPy.
- PyOut CuPy (Python) processa PY_ARRAY_* com CuPy (fallback NumPy).

Arvore (PyOut)
--------------
PyMql-CodeBridge/
  README.md
  PROTOCOL.md
  CMDMT.md
  docs/
    PROTOCOL_ARRAY.md
    PYINCUPY.md
  pyout/
    pyout_server.py
    pyout_client.py
    registry.py
    commands.py
    arrays.py
  pyout_cupy/
    pyout_cupy_server.py
    pyout_cupy_cli.py
  pyincupy/
    PyInCupyServiceBridge.mq5

Arquitetura
-----------

[Python PyInClient]  ->  [MT5 PyInServerService :9091]
[MT5 indicador (PyOutClient)]  ->  [PyOutService :9100]

[MT5 indicador (cliente)] -> [PyInCupyServiceBridge :9091] -> [PyOut CuPy :9200]

- O canal PyIn (9091) é exclusivo para Python -> MT5.
- O canal PyOut (9100) é exclusivo para MT5 -> Python.
- Sem bridge dentro do MT5: cada lado conecta direto no seu servidor.

Componentes
-----------
- MT5 service (PyInServer):
  - arquivo: mt5/Services/PyInServerService.mq5
- Python client (PyInClient):
  - arquivo: PyMql-CodeBridge/pyin/pyin_client.py
- Python bridge (PyOut):
  - PyMql-CodeBridge/pyout/pyout_server.py
  - PyMql-CodeBridge/pyout/pyout_cli.py (start/stop/status/ping/ensure)
  - registry: PyMql-CodeBridge/pyout/registry.py
  - commands: PyMql-CodeBridge/pyout/commands.py
  - arrays: PyMql-CodeBridge/pyout/arrays.py
  - wrappers legacy: python/legado/python_bridge_server.py + python/legado/mt5_bridge.py

- MT5 service (CuPy bridge):
  - PyMql-CodeBridge/pyincupy/PyInCupyServiceBridge.mq5
- Python server (PyOut CuPy):
  - PyMql-CodeBridge/pyout_cupy/pyout_cupy_server.py
  - PyMql-CodeBridge/pyout_cupy/pyout_cupy_cli.py
  - docs/PYINCUPY.md

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

Fluxo de array (via PyOut)
--------------------------
1) MT5 (cliente) -> PyOut: PY_ARRAY_SUBMIT (frame binario)
2) MT5 (cliente) -> PyOut: PY_ARRAY_POLL (frame binario)
3) PyOut -> MT5: PY_ARRAY_RESP / PY_ARRAY_PENDING (frame binario)

CLI (cmdmt)
-----------
Todos os comandos Python ficam sob o namespace "python" (ou "py"):

- python service <ping|cmd|raw|compile> [args...]
- python bridge <start|stop|status|ping|ensure> [host] [port]
- python build -i NOME [--buffers N]   (scaffold STFFT)

Exemplo (scaffold STFFT):
  cmdmt python build -i MeuIndicador --buffers 2

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
