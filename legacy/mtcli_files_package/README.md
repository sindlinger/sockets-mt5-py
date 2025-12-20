# MTCLI (por arquivos) — EA que executa comandos + CLI externo

Este pacote te dá um "telnet" simples para o MetaTrader 5 **sem sockets**:

- Você roda um **EA** no MT5: `CommandListener.mq5`
- Você roda um **CLI** fora do MT5 (Python): `mtcli_files.py`
- O CLI escreve `cmd_*.txt` em `MQL5\Files`
- O EA lê, executa o comando, e escreve `resp_*.txt`

## 1) Instalação no MT5

1. No MT5: **File → Open Data Folder**
2. Copie `MQL5/Experts/CommandListener.mq5` para:
   - `<DataFolder>\MQL5\Experts\CommandListener.mq5`
3. Compile no MetaEditor.
4. Anexe o EA em qualquer gráfico (pode ser BTCUSD, EURUSD, etc).

No log (Aba **Experts**) ele imprime algo assim:

`CommandListener iniciado. Files=C:\Users\...\MetaQuotes\Terminal\...\MQL5\Files`

👉 Esse caminho é o que você passa para o CLI.

## 2) Rodando o CLI (fora)

### Em Windows (PowerShell / CMD):
```bash
python mtcli_files.py --dir "C:\Users\...\MQL5\Files"
```

### Em WSL (Linux):
```bash
python3 mtcli_files.py --dir "C:\Users\...\MQL5\Files"
# ou já convertido:
python3 mtcli_files.py --dir "/mnt/c/Users/.../MQL5/Files"
```

O script tenta converter `C:\...` usando `wslpath -u` quando possível.

## 3) Comandos (no CLI)

- `ping`
- `open EURUSD H1`
- `charts`
- `buy EURUSD 0.01`
- `sell EURUSD 0.01`
- `positions`
- `closeall`
- `quit`

Observação: no `buy/sell`, `sl` e `tp` (se você passar) são **preços**, não pontos.

## 4) Como o EA abre um gráfico?

Ele usa:

- `SymbolSelect(symbol,true)` para garantir que o símbolo esteja no Market Watch.
- `ChartOpen(symbol, timeframe)` para abrir o gráfico.

O handler `H_OpenChart` fica dentro do `CommandListener.mq5`.

## Segurança

Teste primeiro em **conta demo**.
