@echo off
REM Wrapper simples para executar cmdmt.py no Windows
setlocal
python "C:\mql\mt5-shellscripts\sockets-python\python\cmdmt.py" %*
