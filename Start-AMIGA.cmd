@echo off
setlocal
cd /d "%~dp0"
if /I "%~1"=="preview" goto preview
call Start-Backend.cmd
exit /b %errorlevel%
:preview
where node >nul 2>nul
if %errorlevel% equ 0 (
  node frontend\scripts\server.mjs
) else (
  if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" (
    "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" frontend\scripts\server.mjs
  ) else (
    echo Node.js 22 atau lebih baru belum ditemukan.
  )
)
pause
