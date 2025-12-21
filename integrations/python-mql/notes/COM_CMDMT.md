# Integração Python <-> MT5 (com CMDMT)

Este fluxo descreve o uso do **cmdmt** como CLI/cliente para falar com o serviço MT5 e/ou com o Python‑Bridge.

## 1) CMDMT -> MT5 (serviço principal)

`python/cmdmt.py` envia comandos para o serviço MQL (porta **9090**):

- `ping`
- `open`, `attachind`, `attachea`, `applytpl`, etc.
- `py PAYLOAD` (envia `PY_CALL`)

### Exemplo
```
python python/cmdmt.py --host host.docker.internal --port 9090 --seq "ping"
```

## 2) CMDMT -> serviço Python-only (9091)

Comandos:

```
pyservice ping [HOST] [PORT]
pyservice cmd TYPE [PARAMS...]
pyservice raw LINE
```

Isso fala direto com `OficialTelnetServicePySocket.mq5`.

## 3) CMDMT -> Python Bridge (9100)

Comandos:

```
pybridge start|stop|status
pybridge ping [HOST] [PORT]
pybridge ensure [HOST] [PORT]
```

Isso inicia/checa o `python/python_bridge_server.py`.

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

## Quando usar

- Você quer um fluxo rápido no terminal.
- Você quer comandos prontos para anexar indicador/EA sem escrever socket.
- Você quer controlar o bridge Python sem abrir outro console.
