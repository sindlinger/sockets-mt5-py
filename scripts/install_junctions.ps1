param(
  [string]$TerminalPath = ""
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SourceRoot = Join-Path $ProjectRoot "mt5"

if (-not (Test-Path $SourceRoot)) {
  Write-Host "Pasta 'mt5' não encontrada em $ProjectRoot" -ForegroundColor Red
  exit 1
}

if ([string]::IsNullOrWhiteSpace($TerminalPath)) {
  $base = Join-Path $env:APPDATA "MetaQuotes\Terminal"
  $cands = @()
  if (Test-Path $base) {
    $cands = Get-ChildItem $base -Directory | Where-Object { Test-Path (Join-Path $_.FullName "MQL5") }
  }
  if ($cands.Count -eq 1) {
    $TerminalPath = $cands[0].FullName
  } elseif ($cands.Count -gt 1) {
    $TerminalPath = ($cands | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
    Write-Host "Vários terminais encontrados. Usando o mais recente:" -ForegroundColor Yellow
    Write-Host "  $TerminalPath"
  } else {
    Write-Host "Terminal MT5 não encontrado. Passe -TerminalPath." -ForegroundColor Red
    exit 1
  }
}

$Mql5 = Join-Path $TerminalPath "MQL5"
if (-not (Test-Path $Mql5)) {
  Write-Host "Pasta MQL5 não encontrada em $TerminalPath" -ForegroundColor Red
  exit 1
}

$links = @{
  (Join-Path $Mql5 "Services\OficialTelnetServiceSocket") = (Join-Path $SourceRoot "Services\OficialTelnetServiceSocket");
  (Join-Path $Mql5 "Services\OficialTelnetServicePySocket") = (Join-Path $SourceRoot "Services\OficialTelnetServicePySocket");
  (Join-Path $Mql5 "Experts\OficialTelnetListener") = (Join-Path $SourceRoot "Experts\OficialTelnetListener");
  (Join-Path $Mql5 "Scripts\TelnetSocketScripts") = (Join-Path $SourceRoot "Scripts\TelnetSocketScripts");
  (Join-Path $Mql5 "Indicators\TelnetSocketIndicators") = (Join-Path $SourceRoot "Indicators\TelnetSocketIndicators");
}

function Ensure-Dir($path) {
  if (-not (Test-Path $path)) {
    New-Item -ItemType Directory -Force -Path $path | Out-Null
  }
}

foreach ($kv in $links.GetEnumerator()) {
  $link = $kv.Key
  $target = $kv.Value
  Ensure-Dir $target

  if (Test-Path $link) {
    $item = $null
    try {
      $item = Get-Item -LiteralPath $link -Force -ErrorAction Stop
    } catch {
      $item = $null
    }
    if ($null -ne $item -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
      # remove junction safely (rmdir works better for reparse points)
      cmd.exe /c "rmdir `"$link`""
    } else {
      $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
      $backup = $link + ".bak-" + $stamp
      Move-Item $link $backup
      Write-Host "Backup: $link -> $backup" -ForegroundColor Yellow
    }
  }

  if (Test-Path $link) {
    Write-Host "Link já existe, mantendo: $link" -ForegroundColor Yellow
  } else {
    cmd.exe /c "mklink /J `"$link`" `"$target`""
  }
}

# Copia o serviço .mq5 para a raiz de Services (MetaEditor compila melhor assim)
$svcSrc = Join-Path $SourceRoot "Services\\OficialTelnetServiceSocket.mq5"
$svcDst = Join-Path $Mql5 "Services\\OficialTelnetServiceSocket.mq5"
if (Test-Path $svcSrc) {
  if (Test-Path $svcDst) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backup = $svcDst + ".bak-" + $stamp
    Move-Item $svcDst $backup
    Write-Host "Backup: $svcDst -> $backup" -ForegroundColor Yellow
  }
  Copy-Item $svcSrc $svcDst -Force
  Write-Host "Serviço copiado para Services root." -ForegroundColor Green
}

$svcPySrc = Join-Path $SourceRoot "Services\\OficialTelnetServicePySocket.mq5"
$svcPyDst = Join-Path $Mql5 "Services\\OficialTelnetServicePySocket.mq5"
if (Test-Path $svcPySrc) {
  if (Test-Path $svcPyDst) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backup = $svcPyDst + ".bak-" + $stamp
    Move-Item $svcPyDst $backup
    Write-Host "Backup: $svcPyDst -> $backup" -ForegroundColor Yellow
  }
  Copy-Item $svcPySrc $svcPyDst -Force
  Write-Host "Serviço Python copiado para Services root." -ForegroundColor Green
}

Write-Host "Junctions criados com sucesso." -ForegroundColor Green
