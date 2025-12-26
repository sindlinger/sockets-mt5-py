CMDMT (iniciador)
=================

Papel
-----
O cmdmt e' o orquestrador/iniciador. Ele nao faz parte do runtime.

 Ele:
- compila o PyInServer (servico MT5)
- inicia/para o PyOut (via pyout_cli)
- faz ping/testes rapidos (via pyout_cli)
- gera scaffold de indicadores (STFFT)

Runtime real
------------
Depois que tudo esta rodando, o fluxo de runtime e' separado:
  MT5 (indicador/cliente) -> PyOut (Python)
  Python (cliente) -> PyInServer (MT5)

Comandos relevantes
-------------------
- python service <ping|cmd|raw|compile> [args...]
- python bridge <start|stop|status|ping|ensure> [host] [port]  (delegado ao pyout_cli)
- python server [pyout|cupy] <up|down|status|ping|ensure|serve|all> [host] [port] [workers|--workers N] [--cupy|--pyout]
- python start [pyout|cupy] all [host] [port] [workers|--workers N] [--cupy|--pyout]
- python ping|ensure|status [--cupy|--pyout] [host] [port]
- python cupy <up|down|status|ping|ensure|serve> [host] [port]  (delegado ao pyout_cupy_cli)
- python build -i NOME [--buffers N]   (scaffold STFFT)
- compile service NOME   (compila serviço em MQL5/Services)
- service compile NOME   (alias)
- service start NOME     (automation: inicia serviço no MT5)
- service stop NOME      (automation: para serviço no MT5)
- logs pyout|pyin|cupy [--server|--client] [--cupy|--pyout] [N] [filtro...] [--follow]
