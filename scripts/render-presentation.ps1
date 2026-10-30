param(
    [Parameter(Mandatory=$true)][string]$InputPath,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$taskInput = (Resolve-Path -LiteralPath $InputPath).Path
$taskOutput = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $taskOutput | Out-Null
$taskExisting = @(Get-Process -Name POWERPNT -ErrorAction SilentlyContinue).Count -gt 0
$taskPowerPoint = $null
$taskPresentation = $null
try {
    $taskPowerPoint = New-Object -ComObject PowerPoint.Application
    $taskPowerPoint.DisplayAlerts = 1
    $taskPowerPoint.AutomationSecurity = 3
    # Open read-only without a presentation window. No user presentation is modified.
    $taskPresentation = $taskPowerPoint.Presentations.Open($taskInput, -1, 0, 0)
    $taskOverflow = @()
    for ($taskIndex=1; $taskIndex -le $taskPresentation.Slides.Count; $taskIndex++) {
        $taskSlide = $taskPresentation.Slides.Item($taskIndex)
        $taskSlide.Export((Join-Path $taskOutput ('slide-{0:D2}.png' -f $taskIndex)), 'PNG', 1600, 900)
        foreach ($taskShape in $taskSlide.Shapes) {
            if ($taskShape.HasTextFrame -and $taskShape.TextFrame.HasText) {
                if ($taskShape.TextFrame2.TextRange.BoundHeight -gt ($taskShape.Height + 3)) {
                    $taskOverflow += @{slide=$taskIndex; shape=$taskShape.Name; text=$taskShape.TextFrame.TextRange.Text; height=$taskShape.Height; required=$taskShape.TextFrame2.TextRange.BoundHeight}
                }
            }
        }
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($taskSlide)
    }
    ConvertTo-Json -InputObject @($taskOverflow) -Depth 4 | Set-Content -LiteralPath (Join-Path $taskOutput 'overflow.json') -Encoding utf8
    Write-Output ('Rendered {0} slides. Text overflows: {1}. Output: {2}' -f $taskPresentation.Slides.Count, $taskOverflow.Count, $taskOutput)
}
finally {
    if ($taskPresentation) {
        $taskPresentation.Close()
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($taskPresentation)
    }
    if ($taskPowerPoint) {
        if (-not $taskExisting -and $taskPowerPoint.Presentations.Count -eq 0) { $taskPowerPoint.Quit() }
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($taskPowerPoint)
    }
}
