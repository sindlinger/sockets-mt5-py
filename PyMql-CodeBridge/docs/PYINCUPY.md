PyInCupyServiceBridge + PyOut CuPy
=================================

Arquitetura
-----------
[MT5 indicador/EA (cliente)] -> [PyInCupyServiceBridge :9091] -> [PyOut CuPy :9200]

- O indicador/EA conecta no Service (9091).
- O Service conecta no Python (9200) apenas quando precisa.
- Ping (SIM/PNIG) valida o Python antes de aceitar chamadas.

Inicializacao (passo a passo)
-----------------------------
1) Start do Python CuPy:
   python3 PyMql-CodeBridge/pyout_cupy/pyout_cupy_cli.py up --host 0.0.0.0 --port 9200
2) Start do Service no MT5:
   PyInCupyServiceBridge (Services)
3) Carregue o indicador cliente (porta 9091) e dispare SIM para validar:
   -> OK sim_ok pyout=ok

Notas
-----
- Sem auto-connect: o Service so conecta no Python quando recebe SIM/PY_CALL/arrays.
- PING serve como keepalive (controlado por InpPyPingMs).
