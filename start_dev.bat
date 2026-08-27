@echo off
title SMSB IoT Monitoring Platform Launcher
color 0A

echo =========================================================
echo    SMSB IoT Monitoring Platform - Development Launcher
echo =========================================================
echo.

:: 1. Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    pause
    exit /b 1
)

:: 2. Check Node
npm --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js / npm is not installed or not in PATH.
    pause
    exit /b 1
)

:: 3. Launch Backend HubGate V5
echo [1/3] Starting HubGate V5 Central Server on port 8000...
start "HubGate V5 API (Port 8000)" cmd /k "cd /d %~dp0server && python -m uvicorn hubgatev5:api --host 0.0.0.0 --port 8000"

:: 4. Launch Frontend React SPA
echo [2/3] Starting Frontend SPA Dev Server on port 5173...
start "Frontend SPA (Port 5173)" cmd /k "cd /d %~dp0dashboard && npm run dev"

:: 5. Open Browser
echo [3/3] Waiting for servers to initialize...
timeout /t 3 /nobreak >nul
start http://localhost:5173

echo.
echo =========================================================
echo    All Services Started Successfully!
echo    - Frontend SPA:   http://localhost:5173
echo    - HubGate V5 API: http://localhost:8000
echo    - API Docs:       http://localhost:8000/docs
echo.
echo    Credentials:
echo    - Admin:    admin / admin123
echo    - Operator: operator / operator123
echo    - Viewer:   viewer / viewer123
echo.
echo    (Close the opened terminal windows to stop services)
echo =========================================================
echo.
pause
