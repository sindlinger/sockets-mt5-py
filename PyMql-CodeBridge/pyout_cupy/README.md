PyOut CuPy (Python)
===================

Papel
-----
Servidor Python que processa chamadas de arrays (PY_ARRAY_CALL/SUBMIT/POLL)
com suporte a CuPy (GPU). Se CuPy nao estiver disponivel, faz fallback para
NumPy.

Arquivos
--------
- pyout_cupy_server.py
- pyout_cupy_cli.py

Start rapido
------------
Foreground:
  python3 pyout_cupy_server.py 0.0.0.0 9200

Background (via CLI):
  python3 pyout_cupy_cli.py up --host 0.0.0.0 --port 9200
  python3 pyout_cupy_cli.py status
  python3 pyout_cupy_cli.py ping --host host.docker.internal,127.0.0.1 --port 9200

Env vars
--------
- PYOUT_CUPY_BIND (bind host)
- PYOUT_CUPY_PORT
- PYOUT_CUPY_HOSTS (lista para ping/ensure)

Protocolo
---------
- Texto (linha): PING -> PONG
- Frame binario: ver ../docs/PROTOCOL_ARRAY.md
