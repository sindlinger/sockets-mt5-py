#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME=${1:-SocketTelnetService}
ACTION=${2:-Start}
WINDOW_TITLE=${WINDOW_TITLE:-"MetaTrader;MetaQuotes"}
START_KEY=${START_KEY:-"i"}
SERVICES_LABEL=${SERVICES_LABEL:-"Services;Serviços;Servicos"}
START_MENU_LABEL=${START_MENU_LABEL:-"Iniciar;Start"}
STOP_MENU_LABEL=${STOP_MENU_LABEL:-"Parar;Stop"}
STOP_KEY=${STOP_KEY:-""}

PS_EXE=${POWERSHELL_EXE:-/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe}
if [ ! -x "$PS_EXE" ]; then
  echo "powershell.exe não encontrado em $PS_EXE. Defina POWERSHELL_EXE." >&2
  exit 1
fi

SCRIPT_WIN=$(wslpath -w "$(dirname "$0")/mt5_start_service.ps1")

"$PS_EXE" -NoProfile -ExecutionPolicy Bypass -File "$SCRIPT_WIN" \
  -ServiceName "$SERVICE_NAME" \
  -WindowTitle "$WINDOW_TITLE" \
  -Action "$ACTION" \
  -StartKey "$START_KEY" \
  -ServicesLabel "$SERVICES_LABEL" \
  -StartMenuLabel "$START_MENU_LABEL" \
  -StopMenuLabel "$STOP_MENU_LABEL" \
  -StopKey "$STOP_KEY"
