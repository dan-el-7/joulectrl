@echo off
rem joulectrl desktop launcher (Windows) — starts the Electron desktop app.
rem The app spawns the uvicorn API as a child process and cleans it up on exit.
rem Optional overrides (defaults suit the C dev laptop):
rem   JOLECTRL_PORT  - API port (default 8127)
rem   JOUCTRL_PYTHON - python interpreter with fastapi/uvicorn installed
setlocal
cd /d "%~dp0.."
where node >nul 2>&1 || (echo node+npm required in PATH & exit /b 1)
if not exist node_modules\electron\dist\electron.exe (
  echo Installing dependencies ^(first run^)...
  call npm install || exit /b 1
)
call npx electron electron\main.cjs
