
$host.ui.RawUI.WindowTitle = "LF Worker - Port 9232"
$ErrorActionPreference = "SilentlyContinue"
Clear-Host
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "     LOAD FACTOR WORKER - PORT 9232" -ForegroundColor Yellow -BackgroundColor Black
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Monitoring log file: D:\CODERED\LAB\market_insights\outputs\run_generated_291225_at_08.11\logs\ports\9232_stdout.log" -ForegroundColor Gray
Write-Host ""
if (Test-Path "D:\CODERED\LAB\market_insights\outputs\run_generated_291225_at_08.11\logs\ports\9232_stdout.log") {
    Get-Content "D:\CODERED\LAB\market_insights\outputs\run_generated_291225_at_08.11\logs\ports\9232_stdout.log" -Wait -Tail 50
} else {
    Write-Host "Waiting for log file to be created..." -ForegroundColor Yellow
    $timeout = 30
    $elapsed = 0
    while (-not (Test-Path "D:\CODERED\LAB\market_insights\outputs\run_generated_291225_at_08.11\logs\ports\9232_stdout.log") -and $elapsed -lt $timeout) {
        Start-Sleep -Milliseconds 500
        $elapsed += 0.5
        Write-Host "." -NoNewline -ForegroundColor Yellow
    }
    Write-Host ""
    if (Test-Path "D:\CODERED\LAB\market_insights\outputs\run_generated_291225_at_08.11\logs\ports\9232_stdout.log") {
        Write-Host "Log file found! Starting monitor..." -ForegroundColor Green
        Write-Host ""
        Get-Content "D:\CODERED\LAB\market_insights\outputs\run_generated_291225_at_08.11\logs\ports\9232_stdout.log" -Wait -Tail 50
    } else {
        Write-Host "Timeout waiting for log file. Please check if worker is running." -ForegroundColor Red
        Write-Host "Press any key to exit..."
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    }
}
