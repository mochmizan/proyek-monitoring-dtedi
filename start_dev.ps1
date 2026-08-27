# SMSB IoT Monitoring Platform - PowerShell Development Launcher
Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host "   SMSB IoT Monitoring Platform - PowerShell Launcher   " -ForegroundColor Cyan
Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host ""

$rootDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# 1. Detect Local Ethernet / Wi-Fi IP
$localIP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notlike "*Loopback*" -and $_.InterfaceAlias -notlike "*vEthernet*" -and $_.IPAddress -notlike "169.254*" } | Select-Object -First 1).IPAddress
Write-Host "[NETWORK] Local Host IP detected: $localIP" -ForegroundColor Green

# 2. Check Raspberry Pi Hub Reachability
$piIP = "10.33.36.81"
Write-Host "[NETWORK] Checking Raspberry Pi Hub at $piIP..." -NoNewline
if (Test-Connection -ComputerName $piIP -Count 1 -Quiet) {
    Write-Host " [ONLINE]" -ForegroundColor Green
} else {
    Write-Host " [OFFLINE/UNREACHABLE] (Check Ethernet cable / network connection)" -ForegroundColor Yellow
}

# 3. Launch Backend HubGate V5
Write-Host "[1/2] Starting HubGate V5 API on port 8000..." -ForegroundColor White
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$rootDir\server'; Write-Host '--- HubGate V5 Central Gateway (Port 8000) ---' -ForegroundColor Cyan; python -m uvicorn hubgatev5:api --host 0.0.0.0 --port 8000"

# 4. Launch Frontend Vite SPA
Write-Host "[2/2] Starting Frontend SPA on port 5173..." -ForegroundColor White
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$rootDir\dashboard'; Write-Host '--- Frontend Vite SPA (Port 5173) ---' -ForegroundColor Green; npm run dev"

# 5. Open Browser
Start-Sleep -Seconds 3
Start-Process "http://localhost:5173"

Write-Host ""
Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host "   All Services Running!" -ForegroundColor Green
Write-Host "   - Frontend SPA:   http://localhost:5173" -ForegroundColor White
Write-Host "   - HubGate V5 API: http://localhost:8000" -ForegroundColor White
Write-Host "   - API Docs:       http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "   Credentials:" -ForegroundColor Yellow
Write-Host "   - Admin:    admin / admin123" -ForegroundColor Yellow
Write-Host "   - Operator: operator / operator123" -ForegroundColor Yellow
Write-Host "   - Viewer:   viewer / viewer123" -ForegroundColor Yellow
Write-Host "=========================================================" -ForegroundColor Cyan
