param(
  [string]$WindowTitle = "MetaTrader 5"
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

function Find-Window($titlePattern) {
  $root = [System.Windows.Automation.AutomationElement]::RootElement
  $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Window)
  $wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)
  foreach ($w in $wins) {
    if ($w.Current.Name -like "*$titlePattern*") { return $w }
  }
  return $null
}

function Get-WindowText([IntPtr]$hWnd) {
  $sb = New-Object System.Text.StringBuilder 512
  [Win32]::GetWindowText($hWnd, $sb, $sb.Capacity) | Out-Null
  return $sb.ToString()
}

$win = Find-Window $WindowTitle
if (-not $win) { throw "Janela do MT5 nao encontrada (titulo contem '$WindowTitle')." }

[Win32]::SetForegroundWindow($win.Current.NativeWindowHandle) | Out-Null
Start-Sleep -Milliseconds 300

$fg = [Win32]::GetForegroundWindow()
$fgTitle = Get-WindowText $fg
Write-Host "Foreground: $fgTitle"

if ($fg -eq $win.Current.NativeWindowHandle) {
  Write-Host "OK: MT5 ficou em primeiro plano"
} else {
  Write-Host "WARN: MT5 NAO ficou em primeiro plano"
}
