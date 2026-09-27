@echo off
title Apple Watch PC Controller
cd /d "%~dp0\.."
echo ==============================================
echo  Starting Apple Watch PC Controller Service...
echo ==============================================
set "PY=py"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
%PY% -m uvicorn watch_pc_controller.server:app --host 0.0.0.0 --port 8000
pause
