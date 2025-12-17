import socket, json

HOST="127.0.0.1"
PORT=9090

with socket.create_connection((HOST, PORT), timeout=2) as s:
    s.sendall((json.dumps({"cmd":"ping"}) + "\n").encode("utf-8"))
    print(s.recv(4096).decode("utf-8"))
