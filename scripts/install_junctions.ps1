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
    $item = Get-Item $link -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
      Remove-Item $link -Force
    } else {
      $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
      $backup = $link + ".bak-" + $stamp
      Move-Item $link $backup
      Write-Host "Backup: $link -> $backup" -ForegroundColor Yellow
    }
  }

  cmd.exe /c "mklink /J `"$link`" `"$target`""
}

Write-Host "Junctions criados com sucesso." -ForegroundColor Green
