@echo off
setlocal
cd /d "%~dp0"
echo Electronic components catalog
if exist ".venv-windows\Scripts\python.exe" goto run
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1
if not errorlevel 1 (
    py -3 -m venv .venv-windows
    goto created
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1
if not errorlevel 1 (
    python -m venv .venv-windows
    goto created
)
echo Install Python 3.12 or newer from https://www.python.org/downloads/windows/
echo Select "Add python.exe to PATH" during installation, then run this file again.
pause
exit /b 1
:created
if not exist ".venv-windows\Scripts\python.exe" goto failed
:run
if exist ".venv-windows\installed.ok" goto start
echo Installing dependencies. Internet access is required.
".venv-windows\Scripts\python.exe" -m pip install -r backend\requirements.txt
if errorlevel 1 goto failed
echo installed>".venv-windows\installed.ok"
:start
".venv-windows\Scripts\python.exe" launch_windows.py
if errorlevel 1 goto failed
exit /b 0
:failed
echo Startup failed. Copy or photograph the error above and send it in chat.
pause
exit /b 1
