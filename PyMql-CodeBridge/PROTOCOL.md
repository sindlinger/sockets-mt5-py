Protocol: SEND_ARRAY / GET_ARRAY (PyInService)
=============================================

Servico
-------
- PyInService (MT5) em 9091.
- Recebe comandos texto e frames binarios.

Formato texto
-------------
Linha simples com \n:
  id|CMD|p1|p2\n
Exemplo:
  1|PING\n
  2|PY_CALL|{"cmd":"ping"}\n
Frame binario (arrays)
----------------------
Formato:
  0xFF + 4 bytes (header_len big-endian) + header UTF-8 + raw payload

Header:
  id|SEND_ARRAY|name|dtype|count|raw_len
  id|GET_ARRAY|name|dtype|count|raw_len

Campos:
  id      string
  name    nome do array
  dtype   f64 | f32 | i32 | i16 | u8
  count   numero de elementos
  raw_len count * sizeof(dtype)

SEND_ARRAY
----------
- envia o payload apos o header
- o PyIn guarda o "last array"

GET_ARRAY
---------
- pede o ultimo array guardado
- o PyIn responde com frame binario

PyOut (MT5 -> Python)
---------------------
O PyIn abre conexao com o PyOut (porta 9100) quando recebe:
  PY_CALL ou PY_ARRAY_CALL

Fluxo PY_ARRAY_CALL:
  1) Client -> PyIn: SEND_ARRAY
  2) Client -> PyIn: PY_ARRAY_CALL|nome
  3) PyIn -> PyOut: PY_ARRAY_CALL + payload
  4) PyOut -> PyIn: PY_ARRAY_RESP + payload
  5) Client -> PyIn: GET_ARRAY
