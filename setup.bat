@echo off
setlocal
cd /d "%~dp0"

rem MathArchive setup: requirements.txt is a requirements file, not an editable package.
if not exist "%~dp0requirements.txt" (
  echo ERROR: requirements.txt was not found.
  echo Please extract the entire MathArchive ZIP and run setup.bat from that folder.
  pause
  exit /b 1
)

where py >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python Launcher (py) was not found.
  echo Install Python 3.11 or newer, then retry.
  pause
  exit /b 1
)

if not exist "%~dp0.venv\Scripts\python.exe" (
  py -3 -m venv "%~dp0.venv"
  if errorlevel 1 goto :error
)

"%~dp0.venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error

echo Installing dependencies from requirements.txt with pip -r ...
"%~dp0.venv\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 goto :error

"%~dp0.venv\Scripts\python.exe" "%~dp0main.py"
if errorlevel 1 goto :error
exit /b 0

:error
echo.
echo Setup or launch failed. See the error above.
echo For requirements.txt, use: python -m pip install -r requirements.txt
echo Do NOT use: pip install -e .\requirements.txt
pause
exit /b 1
