@echo off
title Apple Watch PC Controller
cd /d "%~dp0\.."
echo ==============================================
echo  Starting Apple Watch PC Controller Service...
echo ==============================================
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo  The project environment .venv is missing. Create it once, in this folder:
    echo    py -m venv .venv
    echo    .venv\Scripts\python -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)
.venv\Scripts\python.exe -m uvicorn watch_pc_controller.server:app --host 0.0.0.0 --port 8000
pause
