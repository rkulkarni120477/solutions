$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskState = Join-Path $taskRoot '.data/local-processes.json'
if (-not (Test-Path -LiteralPath $taskState)) { Write-Host 'No saved local preview processes.'; exit 0 }
foreach ($taskRecord in (Get-Content -LiteralPath $taskState -Raw | ConvertFrom-Json)) {
    $taskProcess = Get-Process -Id $taskRecord.id -ErrorAction SilentlyContinue
    if ($taskProcess -and $taskProcess.StartTime.ToUniversalTime().Ticks -eq ([datetime]$taskRecord.started).ToUniversalTime().Ticks) {
        # The virtualenv launcher creates a Python child that owns the API socket.
        # Stop the verified process tree so the previous port is actually released.
        & taskkill.exe /PID $taskProcess.Id /T /F | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not stop local preview process $($taskProcess.Id)." }
    }
}
Remove-Item -LiteralPath $taskState
Write-Host 'Stopped the saved local preview processes.'
