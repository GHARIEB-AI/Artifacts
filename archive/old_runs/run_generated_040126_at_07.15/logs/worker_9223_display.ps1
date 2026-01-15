
$host.ui.RawUI.WindowTitle = "LF Worker - Port 9223"
$ErrorActionPreference = "SilentlyContinue"
Clear-Host
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "     LOAD FACTOR WORKER - PORT 9223" -ForegroundColor Yellow -BackgroundColor Black
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Monitoring log file: D:\CODERED\LAB\market_insights\outputs\run_generated_040126_at_07.15\logs\ports\9223_stdout.log" -ForegroundColor Gray
Write-Host ""
if (Test-Path "D:\CODERED\LAB\market_insights\outputs\run_generated_040126_at_07.15\logs\ports\9223_stdout.log") {
    Get-Content "D:\CODERED\LAB\market_insights\outputs\run_generated_040126_at_07.15\logs\ports\9223_stdout.log" -Wait -Tail 50
} else {
    Write-Host "Waiting for log file to be created..." -ForegroundColor Yellow
    $timeout = 30
    $elapsed = 0
    while (-not (Test-Path "D:\CODERED\LAB\market_insights\outputs\run_generated_040126_at_07.15\logs\ports\9223_stdout.log") -and $elapsed -lt $timeout) {
        Start-Sleep -Milliseconds 500
        $elapsed += 0.5
        Write-Host "." -NoNewline -ForegroundColor Yellow
    }
    Write-Host ""
    if (Test-Path "D:\CODERED\LAB\market_insights\outputs\run_generated_040126_at_07.15\logs\ports\9223_stdout.log") {
        Write-Host "Log file found! Starting monitor..." -ForegroundColor Green
        Write-Host ""
        Get-Content "D:\CODERED\LAB\market_insights\outputs\run_generated_040126_at_07.15\logs\ports\9223_stdout.log" -Wait -Tail 50
    } else {
        Write-Host "Timeout waiting for log file. Please check if worker is running." -ForegroundColor Red
        Write-Host "Press any key to exit..."
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    }
}
