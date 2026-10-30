@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    call Setup.bat
    if errorlevel 1 exit /b 1
)
if not exist "models\hand_landmarker.task" (
    call Setup.bat
    if errorlevel 1 exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch.ps1"
if errorlevel 1 pause
