param(
  [string]$TitleLike = "Meta",
  [switch]$ListAllPanes
)
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$root = [System.Windows.Automation.AutomationElement]::RootElement
$condWin = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Window)
$wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $condWin)

$idx = 0
foreach ($w in $wins) {
  $name = $w.Current.Name
  if ($TitleLike -and ($name -notlike "*$TitleLike*")) { $idx++; continue }
  Write-Host "[$idx] $name"
  # listar panes
  $condPane = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Pane)
  $panes = $w.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condPane)
  $seen = @{}
  foreach ($p in $panes) {
    $pn = $p.Current.Name
    if ([string]::IsNullOrWhiteSpace($pn)) { continue }
    if (-not $seen.ContainsKey($pn)) {
      $seen[$pn] = $true
      Write-Host "    pane: $pn"
    }
  }
  if (-not $ListAllPanes) { Write-Host "    (use -ListAllPanes para listar todos)" }
  $idx++
}
