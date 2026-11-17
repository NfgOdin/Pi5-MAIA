@echo off
title CarPi5 Network Mode Switcher
cd /d "%~dp0"
python "%~dp0tools\pi5_net_switch.py"
echo.
pause
