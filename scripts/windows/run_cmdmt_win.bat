@echo off
REM Executa o CMD MT no Windows
REM Serviço MT5 direto (9090).
set HOST=127.0.0.1
set PORT=9090

python "C:\mql\mt5-shellscripts\sockets-python\python\cmdmt.py" --host %HOST% --port %PORT%
