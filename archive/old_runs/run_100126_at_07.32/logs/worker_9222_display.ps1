
$host.ui.RawUI.WindowTitle = "LF Worker - Port 9222"
$ErrorActionPreference = "SilentlyContinue"
Clear-Host
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "     LOAD FACTOR WORKER - PORT 9222" -ForegroundColor Yellow -BackgroundColor Black
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Monitoring log file: D:\CODERED\LAB\Artifacts\run_100126_at_07.32\logs\ports\9222_stdout.log" -ForegroundColor Gray
Write-Host ""
if (Test-Path "D:\CODERED\LAB\Artifacts\run_100126_at_07.32\logs\ports\9222_stdout.log") {
    Get-Content "D:\CODERED\LAB\Artifacts\run_100126_at_07.32\logs\ports\9222_stdout.log" -Wait -Tail 50
} else {
    Write-Host "Waiting for log file to be created..." -ForegroundColor Yellow
    $timeout = 30
    $elapsed = 0
    while (-not (Test-Path "D:\CODERED\LAB\Artifacts\run_100126_at_07.32\logs\ports\9222_stdout.log") -and $elapsed -lt $timeout) {
        Start-Sleep -Milliseconds 500
        $elapsed += 0.5
        Write-Host "." -NoNewline -ForegroundColor Yellow
    }
    Write-Host ""
    if (Test-Path "D:\CODERED\LAB\Artifacts\run_100126_at_07.32\logs\ports\9222_stdout.log") {
        Write-Host "Log file found! Starting monitor..." -ForegroundColor Green
        Write-Host ""
        Get-Content "D:\CODERED\LAB\Artifacts\run_100126_at_07.32\logs\ports\9222_stdout.log" -Wait -Tail 50
    } else {
        Write-Host "Timeout waiting for log file. Please check if worker is running." -ForegroundColor Red
        Write-Host "Press any key to exit..."
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    }
}
