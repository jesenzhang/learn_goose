# Clear port 8000 script
$connections = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($connections) {
    Write-Host "Found connections on port 8000:" -ForegroundColor Yellow
    $connections | ForEach-Object {
        $procId = $_.OwningProcess
        Write-Host "  PID: $procId" -ForegroundColor Cyan
        try {
            $proc = Get-Process -Id $procId -ErrorAction Stop
            Write-Host "  Name: $($proc.ProcessName)" -ForegroundColor Cyan
            Write-Host "  Killing..." -ForegroundColor Yellow
            Stop-Process -Id $procId -Force
            Start-Sleep -Milliseconds 500
            Write-Host "  Killed!" -ForegroundColor Green
        } catch {
            Write-Host "  Process not found or already dead" -ForegroundColor Gray
        }
    }
    Write-Host ""
    Write-Host "Verifying port 8000 is clear..." -ForegroundColor Yellow
    Start-Sleep -Seconds 1
    $check = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
    if ($check) {
        Write-Host "Port 8000 still in use. Try restarting your computer." -ForegroundColor Red
    } else {
        Write-Host "Port 8000 is now clear!" -ForegroundColor Green
    }
} else {
    Write-Host "No connections found on port 8000 - port is clear!" -ForegroundColor Green
}
