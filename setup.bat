@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher (py) was not found. Install Python 3.11 or newer, then retry.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 goto :error
)
call ".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error
call ".venv\Scripts\python.exe" main.py
if errorlevel 1 goto :error
exit /b 0
:error
echo.
echo Setup or launch failed. See the error above.
pause
exit /b 1
