Protocol: Binary frames (SEND_ARRAY / GET_ARRAY)

Nota: este protocolo é servido pelo serviço MT5 Python-only
`OficialTelnetServicePySocket` (porta padrão 9091).

Overview
--------
There are two wire formats supported by the MT5 socket service:

1) Text command:
   id|CMD|p1|p2\n

2) Binary frame (for arrays):
   0xFF + 4 bytes header_len (big-endian) + header (UTF-8) + raw payload

Header format
-------------
Header is a UTF-8 string with pipe separators:

  id|SEND_ARRAY|name|dtype|count|raw_len
  id|GET_ARRAY|name|dtype|count|raw_len

Where:
  id      : request id (string)
  name    : array name (string)
  dtype   : f64 | f32 | i32 | i16 | u8
  count   : number of elements
  raw_len : count * sizeof(dtype)

For SEND_ARRAY, after the header you MUST send raw_len bytes of payload.
For GET_ARRAY, the server returns a frame with header + raw bytes.

Byte order
----------
The 4-byte header length is big-endian (network order).
The raw payload is plain binary bytes; endianness is defined by your dtype
encoding on the client side (use little-endian to match MQL5 on Windows).

Example: SEND_ARRAY (Python pseudo-code)
----------------------------------------
  header = f"{id}|SEND_ARRAY|prices|f64|{count}|{raw_len}"
  frame  = b"\\xFF" + len(header).to_bytes(4, "big") + header.encode("utf-8")
  sock.sendall(frame)
  sock.sendall(payload_bytes)

Example: GET_ARRAY response
---------------------------
  0xFF + 4 bytes header_len + header + raw_bytes

Notes
-----
* This is NOT JSON. It is a binary frame protocol.
* The service stores the last received array in memory and can return it.
* See MQL5 implementation:
  mt5/Services/OficialTelnetServiceSocket.mq5
* Example client:
  examples/mt5_frames.py

Python bridge (MT5 -> PY)
-------------------------
MT5 opens a dedicated, duplex connection to Python (port 9100).
Command: PY_ARRAY_CALL

Flow:
  1) Client sends SEND_ARRAY to MT5 (store last array in MT5 service)
  2) Client sends text cmd: PY_ARRAY_CALL [name]
  3) MT5 sends frame to Python:
       id|PY_ARRAY_CALL|name|dtype|count|raw_len + raw payload
  4) Python responds with:
       id|PY_ARRAY_RESP|name|dtype|count|raw_len + raw payload
  5) MT5 stores the response array as the new "last array"
