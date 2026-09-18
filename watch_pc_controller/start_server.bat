@echo off
title Apple Watch PC Controller
cd /d "%~dp0\.."
echo ==============================================
echo  Starting Apple Watch PC Controller Service...
echo ==============================================
py -m uvicorn watch_pc_controller.server:app --host 0.0.0.0 --port 8000
pause
