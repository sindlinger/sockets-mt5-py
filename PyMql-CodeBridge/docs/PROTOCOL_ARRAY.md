Protocol: PyInCupyServiceBridge / PyOut CuPy
============================================

Canais e portas (default)
-------------------------
- PyInCupyServiceBridge (MT5): 9091
- PyOut CuPy (Python): 9200

Formato texto
-------------
Linha simples com \n:
  id|CMD|p1|p2\n
Exemplos:
  1|PING\n
  2|PY_CALL|{"cmd":"ping"}\n
Comandos texto relevantes
-------------------------
- PING -> PONG
- SIM  -> OK sim_ok pyout=ok | ERROR sim_fail pyout=fail
- PY_CALL -> repassa o JSON para o PyOut CuPy

Frame binario (arrays)
----------------------
Formato:
  0xFF + 4 bytes (header_len big-endian) + header UTF-8 + raw payload

Header:
  id|PY_ARRAY_CALL|name|dtype|count|raw_len
  id|PY_ARRAY_SUBMIT|name|dtype|count|raw_len
  id|PY_ARRAY_POLL|job_id|txt|0|0

Campos:
  id      string
  name    nome do array ou job_id
  dtype   f64 | f32 | i32 | i16 | u8
  count   numero de elementos
  raw_len count * sizeof(dtype)

Respostas
---------
- PY_ARRAY_RESP    (payload com dados)
- PY_ARRAY_ACK     (job_id)
- PY_ARRAY_PENDING
- PY_ARRAY_ERROR   (payload texto)
