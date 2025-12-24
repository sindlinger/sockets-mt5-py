# Integração Python <-> MT5 (sem CMDMT)

Este fluxo descreve como **Python conversa diretamente com MT5** sem usar o CLI `cmdmt`.

## 1) Python -> MT5 (comando direto)

Você abre socket no serviço MQL e envia a mesma linha que o cmdmt envia:

```
ID|TIPO|param1|param2|...
```

- Serviço principal (socket): **9090**
  - `mt5/Services/OficialTelnetServiceSocket.mq5`
- Serviço **PyInService / pyin** (socket): **9091**
  - `mt5/Services/OficialTelnetServicePySocket.mq5`

**Exemplo de linha** (texto simples):
```
1730000000000_1234|PING
```

O retorno é:
```
OK\n<mensagem>\n<dados...>
```

## 2) MT5 -> Python (cálculo/arrays)

Quando o serviço MQL precisa do Python, ele envia `PY_CALL` ou `PY_ARRAY_CALL` para o **PyOutService / pyout**:

- `python/python_bridge_server.py` (PyOutService / pyout, porta **9100** por padrão)
- handlers/registry em `python/mt5_bridge.py`

Fluxo típico:

```
MQL -> PY_ARRAY_CALL -> Python
Python -> PY_ARRAY_RESP -> MQL
```

Se o payload for array, o serviço usa frame binário (prefixo 0xFF + header). O Python recebe, processa e responde.

### FFT com GPU (Python)

O handler `fft` já usa **GPU automaticamente** se o `cupy` estiver disponível.  
Você pode forçar GPU explicitamente no nome do array:

```
fft?gpu=1
```

Ou usar o alias:

```
fft_gpu
```

## 3) Alternativo por arquivo (sem socket)

- `python/pyfft_file_bridge.py`
- Usa `MQL5/Files` como ponte (MQL escreve arquivo / Python lê / Python responde)

## Quando usar

- Você quer integrar direto, sem CLI no meio.
- Você vai controlar tudo via código Python (socket).
