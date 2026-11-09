@echo off
setlocal
cd /d "%~dp0"
net session >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Administrator rights required.
  echo         Right click this file and choose "Run as administrator".
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall_winusb.ps1"
echo.
pause
