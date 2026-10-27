@echo off
setlocal
cd /d "%~dp0"
if not exist ".runtime-temp" mkdir ".runtime-temp"
set "TEMP=%CD%\.runtime-temp"
set "TMP=%TEMP%"
if not exist ".venv\Scripts\python.exe" (
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 -m venv .venv
  ) else (
    if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
      "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m venv .venv
    ) else (
      python -m venv .venv
    )
  )
)
if not exist ".venv\Scripts\python.exe" goto failed
".venv\Scripts\python.exe" -m ensurepip --upgrade
".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -c "from backend.app import create_app; create_app({'START_QUEUE_WORKER': False}); print('Skema lokal siap atau skema PostgreSQL yang sudah ada berhasil diperiksa.')"
if errorlevel 1 goto failed
echo Setup selesai. Jalankan Start-Backend.cmd.
pause
exit /b 0
:failed
echo Setup gagal. Periksa Python 3.12+ dan koneksi internet. Baca pesan di atas.
pause
exit /b 1
