@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Jalankan Setup-Backend.cmd terlebih dahulu.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m backend.manage doctor
pause
