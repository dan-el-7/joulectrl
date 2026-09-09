#!/usr/bin/env bash
# launch_dashboard.sh — one-command joulectrl dashboard launch (Agent A).
#
# Brings up everything in the right order and opens the dashboard in your
# browser:
#   1. venv + deps (created on first run)
#   2. root helper daemon (ONE pkexec prompt; passwordless via the polkit
#      rule that matches ONLY this clone's helper/daemon.py path)
#   3. frontend build (frontend/dist) if missing and npm is available
#   4. API server on 127.0.0.1:8000 (never exposed externally)
#   5. opens http://127.0.0.1:8000 in your default browser
#
# Already-running helper/server are detected and reused (idempotent).
# If anything goes wrong mid-flight, the helper can always be reset with:
#   python3 -m helper.client restore

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # repo root
cd "$HERE"

PORT=8000
URL="http://127.0.0.1:$PORT"

say() { printf '\033[1;34m[joulectrl]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[joulectrl]\033[0m %s\n' "$*" >&2; exit 1; }

# --- 1. venv -------------------------------------------------------------
if [ ! -x .venv/bin/python ]; then
    say "creating virtualenv (.venv)..."
    python3 -m venv .venv
fi
PY="$HERE/.venv/bin/python"
if ! "$PY" -c "import fastapi" 2>/dev/null; then
    say "installing dependencies (first run only)..."
    .venv/bin/pip install -q -e . fastapi uvicorn httpx
fi

# --- 2. root helper (one pkexec prompt) ----------------------------------
say "checking privileged helper..."
if "$PY" -m helper.client read_energy >/dev/null 2>&1; then
    say "helper daemon already running ✓"
else
    say "helper not running — launching (enter your password at the prompt; once per boot)..."
    # NOTE: the polkit rule matches this exact path — do not change it.
    pkexec "$HERE/helper/daemon.py" &
    HELPER_PID=$!
    for i in $(seq 1 30); do
        if "$PY" -m helper.client read_energy >/dev/null 2>&1; then break; fi
        sleep 0.5
    done
    if "$PY" -m helper.client read_energy >/dev/null 2>&1; then
        say "helper daemon up ✓"
    else
        die "helper did not come up (did the pkexec prompt succeed?)"
    fi
fi

# --- 3. frontend build ----------------------------------------------------
if [ -d frontend/dist ]; then
    say "frontend build present ✓"
elif command -v npm >/dev/null 2>&1; then
    say "building frontend (frontend/dist missing)..."
    (cd frontend && npm ci --no-fund --no-audit && npm run build) \
        || say "WARN: frontend build failed — API + /docs will still run"
else
    say "WARN: no frontend/dist and no npm — starting API only (dashboard UI unavailable; /docs works)"
fi

# --- 4. API server --------------------------------------------------------
if curl -sf -o /dev/null "$URL"; then
    say "API already running on :$PORT ✓ (reusing)"
else
    say "starting API on 127.0.0.1:$PORT..."
    nohup "$HERE/.venv/bin/uvicorn" api.app:app --host 127.0.0.1 --port $PORT \
        >/tmp/joulectrl-api.log 2>&1 &
    echo $! > /tmp/joulectrl-api.pid
    for i in $(seq 1 40); do
        if curl -sf -o /dev/null "$URL" || curl -sf -o /dev/null "$URL/docs"; then break; fi
        sleep 0.5
    done
    curl -sf -o /dev/null "$URL" || curl -sf -o /dev/null "$URL/docs" \
        || die "API did not start — see /tmp/joulectrl-api.log"
    say "API up ✓ (log: /tmp/joulectrl-api.log, pid: $(cat /tmp/joulectrl-api.pid))"
fi

# --- 5. open the dashboard -------------------------------------------------
say "opening $URL in your browser..."
xdg-open "$URL" >/dev/null 2>&1 || say "open it manually: $URL"

say "dashboard ready — helper ✓ API ✓ UI at $URL"
say "stop the API later with: kill \$(cat /tmp/joulectrl-api.pid)"
