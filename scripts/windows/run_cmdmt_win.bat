@echo off
REM Executa o CLI unificado CMD MT no Windows
REM Ajuste HOST/PORT abaixo se quiser usar o gateway (9095) ou serviço direto (9090).

set HOST=host.docker.internal
set PORT=9090

set CMDMT_HELLO=0
python "C:\mql\mt5-shellscripts\sockets-python\python\cmdmt.py" --host %HOST% --port %PORT%
