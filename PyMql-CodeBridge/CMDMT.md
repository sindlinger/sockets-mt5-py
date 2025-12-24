CMDMT (iniciador)
=================

Papel
-----
O cmdmt e' o orquestrador/iniciador. Ele nao faz parte do runtime.

Ele:
- compila o PyIn (servico MT5)
- inicia/para o PyOut (python bridge)
- faz ping/testes rapidos
- gera scaffold de indicadores (ex.: stfft)

Runtime real
------------
Depois que tudo esta rodando, o fluxo de runtime e' somente:
  PyIn (MT5) <-> PyOut (Python)

Comandos relevantes
-------------------
- python service <ping|cmd|raw|compile> [args...]
- python bridge <start|stop|status|ping|ensure> [host] [port]
- python build -i stfft [NOME] [--buffers N]
