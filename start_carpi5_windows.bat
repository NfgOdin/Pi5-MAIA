@echo off
title CarPi5 Cockpit & R.U.M. AI Companion (PC Development Server)
cd /d "%~dp0"

echo =====================================================================
echo  🏎️ CarPi5 Dodge Dart Cockpit & R.U.M. AI Companion
echo  Windows Local Development & Simulation Server
echo =====================================================================
echo.
echo Starting Python backend daemon on port 8080...
echo.

:: Get local IP address for phone connection
for /f "tokens=4" %%a in ('route print ^| findstr 0.0.0.0 ^| findstr /v "Default"') do (
    set LOCAL_IP=%%a
    goto :found_ip
)
:found_ip

echo [SUCCESS] Local Web Server is LIVE:
echo   - PC Browser:    http://localhost:8080/index.html
echo   - Phone Browser: http://%LOCAL_IP%:8080/index.html (when on same Wi-Fi)
echo.
echo Launching default browser...
start http://localhost:8080/index.html
echo.
echo Press Ctrl+C in this window to stop the server.
echo =====================================================================
python backend/daemon.py
pause
