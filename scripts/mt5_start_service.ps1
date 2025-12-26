param(
  [string]$ServiceName = "SocketTelnetService",
  [string]$WindowTitle = "MetaTrader",
  [string]$Action = "Start",
  [int]$TimeoutSec = 10,
  [string]$StartKey = "i",
  [string]$ServicesLabel = "Services;Serviços",
  [string]$StartMenuLabel = "Iniciar;Start",
  [string]$StopMenuLabel = "Parar;Stop",
  [string]$NavigatorLabel = "Navigator;Navegador",
  [switch]$ForceNavigatorFocus = $true,
  [int]$MenuScanTimeoutMs = 800,
  [switch]$RequireForeground = $true,
  [int]$ForegroundTimeoutMs = 800,
  [switch]$Verbose,
  [string]$StopKey = ""
)

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class Win32 {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll", SetLastError=true, CharSet=CharSet.Auto)]
  public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
}
"@

function Get-WindowText([IntPtr]$hWnd) {
  $sb = New-Object System.Text.StringBuilder 512
  [Win32]::GetWindowText($hWnd, $sb, $sb.Capacity) | Out-Null
  return $sb.ToString()
}

function Find-Window($titlePattern) {
  $root = [System.Windows.Automation.AutomationElement]::RootElement
  $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Window)
  $wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)
  foreach ($w in $wins) {
    if ($w.Current.Name -like "*$titlePattern*") { return $w }
  }
  return $null
}

function Get-AllWindows() {
  $root = [System.Windows.Automation.AutomationElement]::RootElement
  $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Window)
  return $root.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)
}

function Find-WindowCandidates($patterns) {
  $wins = Get-AllWindows
  $cands = @()
  foreach ($w in $wins) {
    foreach ($p in $patterns) {
      if ($w.Current.Name -like "*$p*") { $cands += $w; break }
    }
  }
  return $cands
}

function Find-First($root, $name, $controlType) {
  $condName = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, $name)
  $condType = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, $controlType)
  $cond = New-Object System.Windows.Automation.AndCondition($condName, $condType)
  return $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
}

function Find-FirstByContains($root, $namePart, $controlType) {
  $condType = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, $controlType)
  $all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condType)
  foreach ($el in $all) {
    if ($el.Current.Name -like "*$namePart*") { return $el }
  }
  return $null
}

function Find-MenuItemByNameWithin($win, $labels, $timeoutMs) {
  $deadline = (Get-Date).AddMilliseconds($timeoutMs)
  while ((Get-Date) -lt $deadline) {
    # tenta localizar menu sob a janela do MT5
    $condMenu = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Menu)
    $menus = $win.FindAll([System.Windows.Automation.TreeScope]::Subtree, $condMenu)
    foreach ($menu in $menus) {
      $condItem = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::MenuItem)
      $items = $menu.FindAll([System.Windows.Automation.TreeScope]::Subtree, $condItem)
      foreach ($lab in $labels) {
        foreach ($it in $items) {
          if ($it.Current.Name -eq $lab) { return $it }
        }
      }
    }
    Start-Sleep -Milliseconds 50
  }
  return $null
}

function Find-Navigator($win, $labels) {
  foreach ($lab in $labels) {
    $nav = Find-First $win $lab ([System.Windows.Automation.ControlType]::Pane)
    if ($nav) { return $nav }
  }
  return $null
}

$titlePatterns = $WindowTitle.Split(';') | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
$fallbackPatterns = @("MetaTrader", "MT5", "Terminal")

$deadline = (Get-Date).AddSeconds($TimeoutSec)
$win = $null
while (-not $win -and (Get-Date) -lt $deadline) {
  foreach ($tp in $titlePatterns) {
    $win = Find-Window $tp
    if ($win) { break }
  }
  if (-not $win) { Start-Sleep -Milliseconds 200 }
}
if (-not $win) {
  # tenta foreground se contiver padrao
  $fg = [Win32]::GetForegroundWindow()
  if ($fg -ne [IntPtr]::Zero) {
    $fgTitle = Get-WindowText $fg
    foreach ($p in $fallbackPatterns) {
      if ($fgTitle -like "*$p*") {
        $all = Get-AllWindows
        foreach ($w in $all) {
          if ($w.Current.Name -eq $fgTitle) { $win = $w; break }
        }
        if ($win) { break }
      }
    }
  }
}
if (-not $win) {
  $cands = Find-WindowCandidates $titlePatterns
  if (-not $cands -or $cands.Count -eq 0) { $cands = Find-WindowCandidates $fallbackPatterns }
  if ($cands -and $cands.Count -ge 1) {
    if ($Verbose) {
      Write-Host "Candidatos de janela:" -ForegroundColor Yellow
      foreach ($c in $cands) { Write-Host "  - $($c.Current.Name)" }
    }
    # escolhe o primeiro candidato
    $win = $cands[0]
  }
}
if (-not $win) {
  $all = Get-AllWindows
  Write-Host "Janelas encontradas:" -ForegroundColor Yellow
  foreach ($w in $all) { Write-Host "  - $($w.Current.Name)" }
  throw "Janela do MT5 nao encontrada (titulo contem '$WindowTitle')."
}

[Win32]::SetForegroundWindow($win.Current.NativeWindowHandle) | Out-Null

if ($RequireForeground) {
  $start = Get-Date
  while (((Get-Date) - $start).TotalMilliseconds -lt $ForegroundTimeoutMs) {
    $fg = [Win32]::GetForegroundWindow()
    if ($fg -eq $win.Current.NativeWindowHandle) { break }
    Start-Sleep -Milliseconds 50
  }
  $fg2 = [Win32]::GetForegroundWindow()
  if ($fg2 -ne $win.Current.NativeWindowHandle) {
    $fgTitle = Get-WindowText $fg2
    throw "MT5 nao ficou em primeiro plano (janela ativa: '$fgTitle')." 
  }
}

# tenta achar Navigator pane (sem toggle)
$navLabels = $NavigatorLabel.Split(';') | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
$nav = Find-Navigator $win $navLabels

if (-not $nav) {
  if ($RequireForeground) {
    $fg = [Win32]::GetForegroundWindow()
    if ($fg -ne $win.Current.NativeWindowHandle) { throw "MT5 perdeu foco antes do Ctrl+N." }
  }
  # abre Navigator via Ctrl+N (toggle) e verifica
  $wshell = New-Object -ComObject WScript.Shell
  $wshell.SendKeys('^n')
  Start-Sleep -Milliseconds 300
  $nav = Find-Navigator $win $navLabels
}

# se ainda nao achou, espera e tenta mais uma vez sem toggle
if (-not $nav) {
  Start-Sleep -Milliseconds 300
  $nav = Find-Navigator $win $navLabels
}

# se ainda nao achou, tenta um ultimo toggle
if (-not $nav) {
  $wshell = New-Object -ComObject WScript.Shell
  $wshell.SendKeys('^n')
  Start-Sleep -Milliseconds 400
  $nav = Find-Navigator $win $navLabels
}

if (-not $nav) { throw "Navigator nao encontrado." }

# força foco no Navigator (pane)
if ($ForceNavigatorFocus) {
  try {
    $nav.SetFocus()
    Start-Sleep -Milliseconds 100
  } catch {}
}

# procurar service pelo nome (direto no Navigator)
$serviceItem = Find-FirstByContains $nav $ServiceName ([System.Windows.Automation.ControlType]::TreeItem)

# fallback: tentar localizar grupo Services/Servicos e buscar dentro
if (-not $serviceItem) {
  $labels = $ServicesLabel.Split(';') | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
  $servicesItem = $null
  foreach ($lab in $labels) {
    $servicesItem = Find-First $nav $lab ([System.Windows.Automation.ControlType]::TreeItem)
    if ($servicesItem) { break }
  }
  if ($servicesItem) {
    try {
      $exp = $servicesItem.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
      $exp.Expand()
    } catch {}
    $serviceItem = Find-FirstByContains $servicesItem $ServiceName ([System.Windows.Automation.ControlType]::TreeItem)
  }
}

if (-not $serviceItem) { throw "Service '$ServiceName' nao encontrado no Navigator." }

# selecionar item
try {
  $sel = $serviceItem.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
  $sel.Select()
} catch {}
try { $serviceItem.SetFocus() } catch {}

if ($RequireForeground) {
  $fg = [Win32]::GetForegroundWindow()
  if ($fg -ne $win.Current.NativeWindowHandle) { throw "MT5 perdeu foco antes do menu." }
}

# abrir menu contexto
$wshell = New-Object -ComObject WScript.Shell
$wshell.SendKeys('+{F10}')
Start-Sleep -Milliseconds 200

$act = $Action.ToLower()
$labels = if ($act -eq "stop") {
  $StopMenuLabel.Split(';') | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
} else {
  $StartMenuLabel.Split(';') | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
}
$mi = Find-MenuItemByNameWithin $win $labels $MenuScanTimeoutMs
if ($mi) {
  try {
    $inv = $mi.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
    $inv.Invoke()
    if ($Verbose) { Write-Host "[ok] clique em menu: $($mi.Current.Name)" }
    exit 0
  } catch {
    # fallback abaixo
  }
}

# fallback: tecla
if ($act -eq "stop" -and $StopKey -ne "") {
  $wshell.SendKeys($StopKey)
  if ($Verbose) { Write-Host "[ok] stop enviado (tecla $StopKey)" }
} else {
  $wshell.SendKeys($StartKey)
  if ($Verbose) { Write-Host "[ok] start enviado (tecla $StartKey)" }
}
