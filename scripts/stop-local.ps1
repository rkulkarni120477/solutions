$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskState = Join-Path $taskRoot '.data/local-processes.json'
if (-not (Test-Path -LiteralPath $taskState)) { Write-Host 'No saved local preview processes.'; exit 0 }
foreach ($taskRecord in (Get-Content -LiteralPath $taskState -Raw | ConvertFrom-Json)) {
    $taskProcess = Get-Process -Id $taskRecord.id -ErrorAction SilentlyContinue
    if ($taskProcess -and $taskProcess.StartTime.ToUniversalTime().Ticks -eq ([datetime]$taskRecord.started).ToUniversalTime().Ticks) {
        Stop-Process -Id $taskProcess.Id
    }
}
Remove-Item -LiteralPath $taskState
Write-Host 'Stopped the saved local preview processes.'
