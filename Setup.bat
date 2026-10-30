@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3.12 -m venv .venv
    if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto fail
".venv\Scripts\python.exe" setup_project.py
if errorlevel 1 goto fail
".venv\Scripts\python.exe" selftest.py
if errorlevel 1 goto fail
echo Setup completed. Double-click Launch.bat.
exit /b 0
:fail
echo Setup failed. Install Python 3.12 if missing, then review the error above.
pause
exit /b 1
