$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) { throw 'Install Python dependencies first. See README.md.' }
if (-not (Test-Path -LiteralPath 'frontend/dist/index.html')) { throw 'Build the frontend first: npm.cmd --prefix frontend run build' }
if (-not (Test-Path -LiteralPath 'renderer/dist/mermaid.js')) { throw 'Build the renderer first: npm.cmd --prefix renderer run build' }
New-Item -ItemType Directory -Force '.data' | Out-Null
if (Test-Path -LiteralPath '.data/local-processes.json') { throw 'A local preview may already be running. Run scripts/stop-local.ps1 first.' }
$env:PUBLIC_URL = 'http://localhost:8000'
$env:PYTHONPATH = Join-Path $taskRoot 'backend'
$env:EMBEDDED_WORKER = 'true'
if (-not $env:CHROMIUM_PATH) {
  foreach ($taskBrowser in @('C:\Program Files\Google\Chrome\Application\chrome.exe','C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')) {
    if (Test-Path -LiteralPath $taskBrowser) { $env:CHROMIUM_PATH = $taskBrowser; break }
  }
}
$taskApi = Start-Process -FilePath (Join-Path $taskRoot '.venv/Scripts/python.exe') -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000','--no-access-log') -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput '.data/api.log' -RedirectStandardError '.data/api.err.log'
$taskRenderer = Start-Process -FilePath 'node' -ArgumentList @('--env-file-if-exists=../.env','server.mjs') -WorkingDirectory (Join-Path $taskRoot 'renderer') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $taskRoot '.data/renderer.log') -RedirectStandardError (Join-Path $taskRoot '.data/renderer.err.log')
@(@{id=$taskApi.Id; started=$taskApi.StartTime.ToUniversalTime().ToString('o')},@{id=$taskRenderer.Id; started=$taskRenderer.StartTime.ToUniversalTime().ToString('o')}) | ConvertTo-Json | Set-Content -LiteralPath '.data/local-processes.json' -Encoding utf8
Write-Host 'Solution Architect Workspace: http://localhost:8000'
Write-Host 'Logs: .data/api.err.log and .data/renderer.err.log. Stop: scripts/stop-local.ps1'
