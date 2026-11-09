@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" -m dji_mic
  exit /b 0
)
where pythonw >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found. Install Python 3.9+, or use MicSeriesControl.exe.
  pause
  exit /b 1
)
start "" pythonw -m dji_mic
