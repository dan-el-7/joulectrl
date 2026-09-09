#!/usr/bin/env bash
# install_linux_app.sh — install the joulectrl desktop app into GNOME (Agent A).
#
# Creates:
#   ~/.local/share/applications/joulectrl.desktop  (GNOME launcher)
#   ~/.local/share/icons/hicolor/scalable/apps/joulectrl.svg (icon)
#
# The desktop entry launches the Electron wrapper (frontend/electron/main.cjs),
# which spawns the uvicorn API server as a child process and opens the dashboard
# in its own window. The privileged helper is started separately if needed
# (use scripts/launch_dashboard.sh for the full browser+helper flow).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # repo root
FRONTEND="$HERE/frontend"

if [ ! -x "$FRONTEND/node_modules/electron/dist/electron" ]; then
    echo "[joulectrl] Electron binary missing — run: (cd frontend && npm ci && node node_modules/electron/install.js)" >&2
    echo "[joulectrl] (npm's allowScripts feature blocks electron's postinstall; run install.js manually as above)" >&2
    exit 1
fi

# icon
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
mkdir -p "$ICON_DIR"
cp "$FRONTEND/electron/joulectrl.svg" "$ICON_DIR/joulectrl.svg"

# .desktop entry — absolute paths, Terminal off
APP_DIR="$HOME/.local/share/applications"
mkdir -p "$APP_DIR"
cat > "$APP_DIR/joulectrl.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=joulectrl
GenericName=Energy-aware compute controller
Comment=Find the lowest energy needed to get the job done on time
Exec=env JOUCTRL_PYTHON=$HERE/.venv/bin/python $FRONTEND/node_modules/electron/dist/electron $FRONTEND/electron/main.cjs
Icon=joulectrl
Terminal=false
Categories=System;Utility;
StartupWMClass=joulectrl
EOF

update-desktop-database "$APP_DIR" 2>/dev/null || true
echo "[joulectrl] installed: GNOME menu (System/Utilities) -> joulectrl, or: gio launch $APP_DIR/joulectrl.desktop"
