param(
  [string]$WindowTitle = "MetaTrader 5",
  [string]$NavigatorLabel = "Navigator;Navegador"
)
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

function Find-Window($titlePattern) {
  $root = [System.Windows.Automation.AutomationElement]::RootElement
  $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Window)
  $wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)
  foreach ($w in $wins) {
    if ($w.Current.Name -like "*$titlePattern*") { return $w }
  }
  return $null
}

function Find-First($root, $name, $controlType) {
  $condName = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, $name)
  $condType = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, $controlType)
  $cond = New-Object System.Windows.Automation.AndCondition($condName, $condType)
  return $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
}

function Find-Navigator($win, $labels) {
  foreach ($lab in $labels) {
    $nav = Find-First $win $lab ([System.Windows.Automation.ControlType]::Pane)
    if ($nav) { return $nav }
  }
  return $null
}

$win = Find-Window $WindowTitle
if (-not $win) { throw "Janela MT5 nao encontrada" }
$labels = $NavigatorLabel.Split(';') | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
$nav = Find-Navigator $win $labels
if (-not $nav) { throw "Navigator nao encontrado" }

# lista TreeItems diretos dentro do Navigator
$condTree = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::TreeItem)
$items = $nav.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condTree)
$seen = @{}
foreach ($it in $items) {
  $name = $it.Current.Name
  if ([string]::IsNullOrWhiteSpace($name)) { continue }
  if (-not $seen.ContainsKey($name)) {
    $seen[$name] = $true
    Write-Host $name
  }
}
