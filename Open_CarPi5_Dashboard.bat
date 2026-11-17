@echo off
title CarPi5 Dashboard Tunnel (localhost:8080)
cd /d "%~dp0"
python "%~dp0tools\pi5_net_switch.py" 4
echo.
pause
