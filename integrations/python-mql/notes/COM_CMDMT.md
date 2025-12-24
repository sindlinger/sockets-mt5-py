# Integração Python <-> MT5 (com CMDMT)

Este fluxo descreve o uso do **cmdmt** como CLI/cliente para falar com o serviço MT5 (Telnet 9090)
e, opcionalmente, para testes rápidos com o **PyInService / PyOutService**.

## 1) CMDMT -> MT5 (serviço principal)

`python/cmdmt.py` envia comandos para o serviço MQL (porta **9090**):

- `ping`
- `open`, `attachind`, `attachea`, `applytpl`, etc.
- `py PAYLOAD` (envia `PY_CALL`)

### Exemplo
```
python python/cmdmt.py --host host.docker.internal --port 9090 "ping"
```

### Sequência (aspas + ';')
```
python python/cmdmt.py "open EURUSD H1; attachind ZigZag 1"
```

## 2) CMDMT -> PyInService (pyin) (9091)

Comandos:

```
pyservice ping [HOST] [PORT]
pyservice cmd TYPE [PARAMS...]
pyservice raw LINE
```

Isso fala direto com `OficialTelnetServicePySocket.mq5` (**PyInService / pyin**).
Use apenas para **testes rápidos**; o fluxo exclusivo do Python deve conectar direto no 9091
sem depender do cmdmt.

## 3) CMDMT -> PyOutService (pyout) (9100)

Comandos:

```
pybridge start|stop|status
pybridge ping [HOST] [PORT]
pybridge ensure [HOST] [PORT]
```

Isso inicia/checa o `python/python_bridge_server.py` (**PyOutService / pyout**).

## 4) Hotkeys (atalhos CMDMT)

Hotkeys aqui são **atalhos do CMDMT**, não os atalhos da UI do MT5.
Eles executam **sequências de comandos** no serviço.

### Listar ajuda
```
hotkeys
cmd+hotkeys
```

### Salvar uma sequência com nome
```
hotkey save SALVAR "open EURUSD H1; attachind ZigZag 1"
```

### Executar
```
SALVAR
@SALVAR
```

### Sequência inline (sem salvar)
```
hotkey "open EURUSD H1; attachind ZigZag 1"
```

## 5) Config INI (tester)

Grava e lê variáveis do `Terminal/tester.ini` usando o mapeamento do `cmdmt`.

```
ini set Common.Login=123456 Common.Password=xyz Common.Server=MetaQuotes-Demo
ini get Common.Login Common.Password Common.Server
ini list
```

- `ini get` e `ini list` **mascaram** `Common.Password`.

## 6) RUN (tester simples)

O `run` exige **caminho do indicador/EA** (absoluto ou relativo ao cwd).  
Se existir, copia para o terminal interno e executa.

```
python python/cmdmt.py "run C:\...\ZigZag.mq5 --ind EURUSD H1 3 dias"
```

## Quando usar

- Você quer um fluxo rápido no terminal.
- Você quer comandos prontos para anexar indicador/EA sem escrever socket.
- Você quer controlar o bridge Python sem abrir outro console.
