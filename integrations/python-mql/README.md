# Integração Python <-> MQL

Este diretório concentra o que é usado para integrar Python com MQL/MT5 no projeto.

## Peças principais

- MQL (serviços do MT5)
  - `mt5/Services/OficialTelnetServiceSocket/` e `mt5/Services/OficialTelnetServiceSocket.mq5`
    - Serviço principal via socket (porta padrão 9090).
  - `mt5/Services/OficialTelnetServicePySocket/` e `mt5/Services/OficialTelnetServicePySocket.mq5`
    - Serviço dedicado ao Python (porta padrão 9091).

- Python (bridge e SDK)
  - `python/python_bridge_server.py`
    - Bridge Python (porta padrão 9100).
  - `python/mt5_bridge.py`
    - Mini-SDK/registry de handlers do bridge.
  - `python/pyfft_file_bridge.py`
    - Bridge por arquivos (MQL5/Files).

- CLI unificado
  - `python/cmdmt.py`
    - Comandos relevantes:
      - `py PAYLOAD` -> envia `PY_CALL` ao serviço MQL principal.
      - `pyservice ping|cmd|raw` -> fala direto com o serviço Python-only (9091).
      - `pybridge start|stop|status|ping|ensure` -> controla o bridge Python (9100).
    - Hosts/portas via env:
      - `CMDMT_PY_SERVICE_HOSTS`, `CMDMT_PY_SERVICE_PORT`
      - `CMDMT_PY_BRIDGE_HOSTS`, `CMDMT_PY_BRIDGE_PORT`

## Docs úteis

- `docs/PROTOCOL_ARRAY.md`
- `docs/MQL5_RUNTIME_MODEL.md`

## Próximos passos

- Colocar exemplos de fluxo em `integrations/python-mql/notes/`.
