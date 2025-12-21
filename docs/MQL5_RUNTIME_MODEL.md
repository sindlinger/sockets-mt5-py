# MQL5: Modelo de Execução e Eventos (Resumo)

Este documento resume o comportamento de **Services**, **Scripts**, **EAs** e **Indicadores** no MT5 e por que isso importa para a nossa arquitetura (service + cmdmt + Python‑Bridge).

## Resumo por tipo de programa

| Programa | Execução | Observação |
|---|---|---|
| **Service** | Thread separada (1 por service) | Um loop infinito **não trava** outros programas |
| **Script** | Thread separada (1 por script) | Um loop infinito **não trava** outros programas |
| **Expert Advisor (EA)** | Thread separada (1 por EA) | Um loop infinito **não trava** outros programas |
| **Indicator** | **1 thread por símbolo** (todos os indicadores daquele símbolo compartilham) | Um loop infinito **trava todos** os indicadores daquele símbolo |

## Ciclo de vida (carregamento)

1. Ao anexar um programa ao gráfico, ele é carregado na memória.  
2. Variáveis globais são inicializadas (construtores de classes são chamados).  
3. O programa fica aguardando eventos.  
4. **Se não existir ao menos um event handler**, o programa não executa.

## Event Handlers principais

| Tipo | Função | Onde se aplica | Comentário |
|---|---|---|---|
| `int` | `OnInit()` | EA / Indicator | Inicialização |
| `void` | `OnDeinit(int reason)` | EA / Indicator | Finalização |
| `void` | `OnStart()` | Script / Service | Evento único |
| `int` | `OnCalculate(...)` | Indicator | Cálculo do indicador |
| `void` | `OnTick()` | EA | Novo tick |
| `void` | `OnTimer()` | EA / Indicator | Timer |
| `void` | `OnTrade()` | EA | Evento de trade |
| `double` | `OnTester()` | EA | Tester |
| `void` | `OnChartEvent(...)` | EA / Indicator | Evento de gráfico |
| `void` | `OnBookEvent(symbol)` | EA / Indicator | Book |

> **Indicador não pode ter dois `OnCalculate` simultaneamente**.  
> Se definir duas variantes, só a de array é usada.

## Fila de eventos

- Cada **programa** e cada **gráfico** tem sua fila de eventos própria.  
- Eventos são processados em **ordem de chegada**.  
- Eventos do mesmo tipo não duplicam na fila (ex.: `OnTick`, `OnTimer`, `OnChartEvent`).  
- A fila tem tamanho limitado; excesso **descarta eventos**.  
- **Evite loops infinitos** (exceto em **Scripts** e **Services** com `OnStart`).

## Eventos custom (Chart Events)

Além dos eventos padrão, é possível **gerar eventos customizados** para um gráfico e tratá‑los em `OnChartEvent(...)`.

**Como funciona (visão prática):**
- Um EA/Indicador pode **emitir** um evento custom para um gráfico.
- O gráfico **enfileira** esse evento e chama `OnChartEvent(...)` no programa anexado.
- Os parâmetros `id`, `lparam`, `dparam`, `sparam` carregam o payload.

**Para que isso serve no nosso caso:**
- **Desacoplar** ações: o Service manda um comando, o EA recebe e **gera um evento custom** para outra parte do código.
- **Evitar travar** o fluxo: eventos entram na fila e são processados em sequência.
- **Padronizar** uma “API interna” (ex.: `id=1001` para “anexar indicador”, `id=1002` para “aplicar template”, etc.).

**Limite importante:** Services **não recebem** eventos de gráfico (não são ligados a chart).  
Logo, eventos custom são úteis **entre EAs/Indicadores**, não entre Services.

## O que isso ajuda no nosso caso

Este modelo explica **por que** separamos serviços:

1. **Service roda em thread própria** → não trava indicadores/EAs.  
2. **Script também roda em thread própria**, mas só executa uma vez.  
3. **Indicadores compartilham thread por símbolo** → qualquer loop bloqueia todos os indicadores desse símbolo.  

### Impacto prático na nossa arquitetura

- **Service principal (9090)** deve ficar leve e sem loops longos para não atrasar o MT5.  
- **Service Python‑only (9091)** pode fazer trabalho pesado e não afeta o resto.  
- **EA Runner** é útil porque EAs também têm thread própria e podem executar tarefas sob comando do service.  

Em resumo: separar serviços e mover o cálculo pesado para Python evita travar o terminal, e o modelo de eventos do MT5 explica por quê.

## Restrições por tipo de programa (resumo)

**Indicadores** não podem usar funções de trade nem certas funções utilitárias:
- Proibido: `OrderSend`, `OrderCheck`, `OrderCalcMargin/Profit`, `Sleep`, `MessageBox`, `ExpertRemove`, `SendFTP`.

**EAs e Scripts** não podem chamar funções específicas de indicadores:
- Ex.: `SetIndexBuffer`, `IndicatorSet*`, `PlotIndexSet*`, `PlotIndexGet*`.

**Services** não têm eventos de chart e não podem usar:
- `ExpertRemove`, timers (`EventSetTimer`, `EventKillTimer`, etc.)
- Funções de indicador (`SetIndexBuffer`, `IndicatorSet*`, `PlotIndexSet*`).

## Carregar / descarregar programas (resumo)

**Indicadores são carregados** quando:
- são anexados ao gráfico, ou o terminal reinicia com eles;
- um template é aplicado contendo o indicador;
- muda símbolo/timeframe/perfil/conta;
- recompilação do indicador (se estiver anexado);
- alteração de parâmetros de entrada.

**Indicadores são descarregados** quando:
- são removidos, o gráfico fecha, muda perfil/conta;
- um template é aplicado substituindo;
- mudança de símbolo/timeframe no gráfico;
- alteração de parâmetros.

**EAs são carregados** quando:
- anexados ao gráfico, reinício do terminal, template, perfil/conta.

**EAs são descarregados** quando:
- removidos, outro EA anexado no mesmo chart, template aplicado, gráfico fechado, troca de perfil/conta, `ExpertRemove()`.

**Scripts**:
- carregam ao anexar e descarregam ao terminar (`OnStart` apenas).

**Services**:
- carregam quando iniciados no menu de Services e podem ficar em loop no `OnStart`.
