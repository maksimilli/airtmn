@echo off
setlocal
cd /d "%~dp0"
echo Electronic components catalog
if exist ".venv-windows\Scripts\python.exe" (
    ".venv-windows\Scripts\python.exe" start_windows.py
    goto finished
)
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    py -3 start_windows.py
    goto finished
)
python -c "import sys" >nul 2>&1
if not errorlevel 1 (
    python start_windows.py
    goto finished
)
echo Install Python 3.12 using "Windows installer (64-bit)" from:
echo https://www.python.org/downloads/release/python-31210/
echo Keep "Python Launcher" selected, then run this file again.
pause
exit /b 1
:finished
if errorlevel 1 goto failed
exit /b 0
:failed
echo Startup failed. Read the instructions above or photograph the error and send it in chat.
pause
exit /b 1
