# Status atual (cmdmt / services / tester)

Este documento resume as mudancas aplicadas ate agora no repo **sockets-python** para o fluxo MT5 + cmdmt + Python.

## 1) Servico principal (OficialTelnetServiceSocket)

Arquivo: `mt5/Services/OficialTelnetServiceSocket/ServiceHandlers.mqh`

- **attachind**: continua criando o indicador direto via `iCustom/IndicatorCreate`.
  - Se o nome nao tem barra, tenta `Examples\\<nome>` como fallback.
  - **Nao copia** indicador de outro MT5. So enxerga `MQL5/Indicators` do terminal onde o servico roda.
- **attachea**: **so aplica template**. Se nao vier `.tpl`, retorna `tpl_required`.
- **screenshot**: desativado por enquanto para nao bloquear `attachind`.
  - `SCREENSHOT` e `SCREENSHOT_SWEEP` retornam `screenshot disabled`.

## 2) cmdmt.py (CLI)

Arquivo: `python/cmdmt.py`

### 2.1. Sequencia de comandos
- Removido `--seq`.
- Sequencia agora e **apenas** por string com aspas e `;`.
  - Exemplo: `"attachind ZigZag 1; list_charts"`

### 2.2. `run` (tester simples)
- **Agora exige caminho** do indicador/EA.
- Copia o arquivo informado para o **terminal dedicado** e executa no tester.
- Usa **IndicatorStub** para indicadores.
- **Predownload** ligado por padrao (pode desligar com `--no-predownload`).
- Timeout padrao aumentado para **120s**.
- Logs e buffers sao coletados e salvos em `run_logs/`.

### 2.3. `ini` (tester.ini)
- Adicionados comandos:
  - `ini set Section.Key=Valor`
  - `ini get Section.Key`
  - `ini list`
  - `ini sync` (copia `Common.Login/Password/Server` de `Terminal/Config/common.ini` para `Terminal/tester.ini`)

### 2.4. Terminal hardcoded
- `run` usa **terminal dedicado** fixo:
  - `../Terminal` (ou `./Terminal` se existir dentro do repo)
- Nao depende de variaveis de ambiente para localizar o terminal.

## 3) Bootstrap (servico que aciona servicos)

Arquivos novos:
- `mt5/Services/OficialTelnetServiceBootstrap.mq5`
- `scripts/mt5_bootstrap_agent.py`
- `integrations/python-mql/notes/MT5_BOOTSTRAP_SERVICE.md`

Fluxo:
- Service bootstrap escreve `MQL5/Files/bootstrap_request.txt`.
- Agente Python responde e pode:
  - compilar servicos
  - iniciar servicos

## 4) Credenciais do MT5 (terminal dedicado)

- O terminal dedicado usa **`../Terminal/Config/common.ini`**.
- Foi ajustado para **Dukascopy demo** (server `Dukascopy-demo-mt5-1`).
- `ini sync` replica para `../Terminal/tester.ini`.
- Resultado: tester sincroniza e executa.

> Observacao: o arquivo `common.ini` precisa ficar em **UTF-16 LE com BOM**. Evite misturar UTF-16 com ASCII no mesmo arquivo.

## 5) Resultado de teste confirmado

- `run` com `ZigZag` executou com sucesso.
- Buffers salvos em:
  - `../Terminal/Tester/Agent-127.0.0.1-3001/MQL5/Files/cmdmt_buffers.txt`

## 6) Documentacao atualizada

- `README_SERVICOS.md`
- `integrations/python-mql/notes/COM_CMDMT.md`
- `integrations/python-mql/notes/README.md`
- `integrations/python-mql/notes/MT5_BOOTSTRAP_SERVICE.md`

## 7) Limites atuais (sem run)

- **attachind/attachea** **nao** copiam de outros MT5.
- Se o indicador/EA estiver em outra instalacao, precisa copiar/linkar antes.

## 8) Pendencias / proximos ajustes

- Opcao de **copiar/linkar automaticamente** arquivos externos antes de `attachind/attachea`.
- Revisar `attachea` para gerar/aplicar template automaticamente sem exigir `.tpl`.
- Ajustar predownload para ser opcional por comando (ja existe `--no-predownload`).

