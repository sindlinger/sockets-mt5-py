PyInCupyServiceBridge (MT5)
===========================

Papel
-----
Servico MT5 que faz bridge entre clientes MQL5 (indicadores/EAs) e o servidor
Python CuPy (PyOut CuPy). Ele escuta no MT5 e encaminha chamadas/arrays para o
servidor Python.

Arquivo
-------
- PyInCupyServiceBridge.mq5

Instalacao
----------
1) Copie este arquivo para:
   MQL5/Services/PyInCupyServiceBridge.mq5
2) Compile e inicie o Service no MT5.

Portas (default)
----------------
- MT5 Service (entrada MQL/Python): 9091
- PyOut CuPy (Python): 9200

Comandos texto
--------------
- PING -> PONG
- SIM  -> OK sim_ok pyout=ok (ou ERROR sim_fail ...)
- PY_CALL -> repassa para o PyOut CuPy

Obs
---
Este service nao faz auto-connect. Ele so conecta no PyOut CuPy quando precisa,
via SIM/PY_CONNECT/PY_CALL ou chamadas de array.
Veja detalhes em: ../docs/PROTOCOL_ARRAY.md
