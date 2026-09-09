#!/usr/bin/env bash
# joulectrl desktop launcher (Linux/macOS) — starts the Electron desktop app.
# The app spawns the uvicorn API as a child process and cleans it up on exit.
# Python discovery (in order): $JOUCTRL_PYTHON → repo .venv/venv → python3 on PATH.
# Port: $JOLECTRL_PORT (default 8127).
set -euo pipefail
cd "$(dirname "$0")/.."

command -v node >/dev/null 2>&1 || { echo "error: node+npm required in PATH" >&2; exit 1; }
command -v npm  >/dev/null 2>&1 || { echo "error: npm required in PATH" >&2; exit 1; }

if [ ! -x node_modules/electron/dist/electron ]; then
  echo "Installing dependencies (first run)…"
  npm install
fi
exec npx electron electron/main.cjs
