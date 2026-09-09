@echo off
rem joulectrl desktop launcher (Windows) — starts the Electron desktop app.
rem The app spawns the uvicorn API as a child process and cleans it up on exit.
rem Python discovery (in main.cjs): %JOUCTRL_PYTHON% -> repo .venv/venv -> python on PATH.
rem Port: %JOLECTRL_PORT% (default 8127).
setlocal
cd /d "%~dp0.."
where node >nul 2>&1 || (echo node+npm required in PATH & exit /b 1)
if not exist node_modules\electron\dist\electron.exe (
  echo Installing dependencies ^(first run^)...
  call npm install || exit /b 1
)
call npx electron electron\main.cjs
