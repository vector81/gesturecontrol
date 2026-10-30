@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" -m pytest -q
if errorlevel 1 goto fail
".venv\Scripts\python.exe" selftest.py
if errorlevel 1 goto fail
echo All hardware-free checks passed.
pause
exit /b 0
:fail
pause
exit /b 1
