$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $root

while ($true) {
    $completed = 0
    $files = Get-ChildItem -LiteralPath .\results -Filter 'terra_reasoning_*_r*.jsonl' -ErrorAction SilentlyContinue
    foreach ($file in $files) {
        if ($file.Name -match '_r[23]\.jsonl$') {
            $completed += (Get-Content -LiteralPath $file.FullName | Measure-Object -Line).Lines
        }
    }
    $stamp = Get-Date -Format 'HH:mm:ss'
    Write-Output "$stamp completed=$completed/72"
    if ([int]$completed -ge 72) { break }
    Start-Sleep -Seconds 45
}
