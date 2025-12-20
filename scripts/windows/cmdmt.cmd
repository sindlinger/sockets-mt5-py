@echo off
REM Wrapper simples para executar cmdmt.py no Windows
setlocal
set CMDMT_HELLO=0
python "C:\mql\mt5-shellscripts\sockets-python\python\cmdmt.py" --host host.docker.internal --port 9090 %*
