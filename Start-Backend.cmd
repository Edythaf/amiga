@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Jalankan Setup-Backend.cmd terlebih dahulu.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m backend.manage doctor
if errorlevel 1 (
  echo Konfigurasi database tidak valid. Perbaiki backend\.env terlebih dahulu.
  pause
  exit /b 1
)
echo AMIGA demo lokal: http://localhost:5002/login
echo Alternatif loopback: http://127.0.0.1:5002/login
echo Buat passwordmu sendiri pada halaman aktivasi yang akan terbuka.
".venv\Scripts\python.exe" -m backend.manage serve --port 5002 --open-browser --reload
pause
