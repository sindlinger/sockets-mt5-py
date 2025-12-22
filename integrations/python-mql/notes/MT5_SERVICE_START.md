# Start de servicos MT5 (one-shot)

Objetivo: iniciar um servico do MT5 **com um unico comando**, via UI automation.

## One-shot (recomendado)

WSL:
```
scripts/mt5_start_service.sh OficialTelnetServicePySocket
```

PowerShell direto:
```
C:\mql\mt5-shellscripts\sockets-python\scripts\mt5_start_service.ps1 -ServiceName "OficialTelnetServicePySocket"
```

Esse comando faz o fluxo completo:
1) encontra a janela do MT5
2) coloca o MT5 em primeiro plano
3) foca o **Navegador**
4) seleciona o servico pelo nome
5) abre o menu de contexto
6) clica em **Iniciar/Start** (ou tecla fallback)

## Variaveis e ajustes

- `WINDOW_TITLE` (titulo da janela do MT5)
- `NAVIGATOR_LABEL` (Navigator/Navegador)
- `START_MENU_LABEL` (Iniciar/Start)
- `START_KEY` (letra de menu, default: `i`)

Exemplo:
```
WINDOW_TITLE="MetaQuotes-Demo: Conta Demo" \
NAVIGATOR_LABEL="Navegador" \
START_MENU_LABEL="Iniciar;Start" \
START_KEY=i \
 scripts/mt5_start_service.sh OficialTelnetServiceSocket
```

## Observacoes importantes

- O servico precisa **existir no Navigator** (adicionado uma vez manualmente).
- O script **nao clica em outras janelas**. Se o MT5 nao ficar em foco, ele aborta.
- O foco do **Navegador** e do item do servico eh forçado antes do menu.

## Ferramentas de diagnostico (opcionais)

- `scripts/mt5_focus_check.ps1` -> confirma se o MT5 ficou em primeiro plano.
- `scripts/mt5_ui_scan.ps1` -> lista janelas e panes (descobrir titulo/labels).
- `scripts/mt5_nav_items.ps1` -> lista itens do Navigator (para achar nome correto).

