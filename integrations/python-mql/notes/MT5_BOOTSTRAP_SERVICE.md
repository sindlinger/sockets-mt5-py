# Bootstrap de servicos (3o servico)

Objetivo: um **servico dedicado** so para **compilar** e **iniciar** outros servicos (socket/PyInService),
sem misturar logica no servico principal.

## Componentes
- **MT5 (MQL5)**: `mt5/Services/OficialTelnetServiceBootstrap.mq5`
  - One-shot: escreve um request em `MQL5/Files/bootstrap_request.txt` e aguarda resposta.
- **Host agent (Python)**: `scripts/mt5_bootstrap_agent.py`
  - Observa o request, executa `cmdmt compile all` e inicia servicos via UI automation (`scripts/mt5_start_service.sh`).
  - Escreve `MQL5/Files/bootstrap_response.txt`.

## Fluxo
1. Usuario inicia **OficialTelnetServiceBootstrap** no MT5 (uma vez).
2. Servico escreve:
   - `action=bootstrap`
   - `compile=1`
   - `services=OficialTelnetServiceSocket;OficialTelnetServicePySocket` (PyInService / pyin)
3. `mt5_bootstrap_agent.py` processa:
   - Compila (`python python/cmdmt.py compile all`)
   - Inicia serviços no Navigator (UI automation)
4. Resposta e gravada em `bootstrap_response.txt` e o servico imprime no Journal.

## Como rodar o agent
```bash
python scripts/mt5_bootstrap_agent.py
```

One-shot (processa um request e sai):
```bash
python scripts/mt5_bootstrap_agent.py --once
```

## Variaveis uteis
- `CMDMT_MT5_DATA` ou `MT5_DATA_DIR` -> data dir do MT5 (Terminal/XXXX)
- `CMDMT_MT5_WINDOW` -> titulo da janela do MT5 (para focar)
- `CMDMT_MT5_START_KEY` -> tecla do menu "Start/Iniciar" (default: `i`)

## Request/Response (arquivos)
**Request** (`bootstrap_request.txt`):
```
action=bootstrap
compile=1
services=OficialTelnetServiceSocket;OficialTelnetServicePySocket
time=2025-12-22 10:00:00
```

**Response** (`bootstrap_response.txt`):
```
ok=1
time=2025-12-22 10:00:05
compile_requested=1
compile_rc=0
start_OficialTelnetServiceSocket=ok
start_OficialTelnetServicePySocket=ok  (PyInService / pyin)
```

Observacao: o bootstrap nao consegue "Start" direto via API. Por isso usa o `mt5_start_service.sh` para operar o UI.
