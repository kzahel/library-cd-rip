@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Please install Python 3.11 or newer from python.org, then open this again.
  pause
  exit /b 1
)
python bootstrap.py
if errorlevel 1 (
  echo Setup could not finish. See the message above.
  pause
  exit /b 1
)
start "" pythonw "%~dp0app.py"
