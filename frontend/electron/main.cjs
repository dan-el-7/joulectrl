/* joulectrl desktop — Electron main process.
 * Spawns the uvicorn API server as a child process and opens the dashboard.
 * Dev machine: python venv at C:/Users/Subhrajyoti/.venvs/joulectrl (see PY env override).
 */
const { app, BrowserWindow, Menu } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');
const isWindows = process.platform === 'win32';

const PORT = parseInt(process.env.JOLECTRL_PORT || '8127', 10);
const PY = process.env.JOUCTRL_PYTHON || 'C:/Users/Subhrajyoti/.venvs/joulectrl/Scripts/python.exe';
// repo root = parent of frontend/
const REPO = path.resolve(__dirname, '..');

let serverProc = null;
let win = null;

function startServer() {
  serverProc = spawn(PY, ['-m', 'uvicorn', 'api.app:app', '--host', '127.0.0.1', '--port', String(PORT)], {
    cwd: REPO,
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });
  serverProc.stdout.on('data', (d) => console.log('[api]', d.toString().trim()));
  serverProc.stderr.on('data', (d) => console.log('[api]', d.toString().trim()));
  serverProc.on('exit', (code) => {
    console.log('[api] exited', code);
    serverProc = null;
    if (win && !app.isQuitting) app.quit();
  });
}

function waitForServer(cb, tries = 0) {
  const req = http.get({ host: '127.0.0.1', port: PORT, path: '/api/capabilities', timeout: 1500 }, (res) => {
    res.resume();
    cb(res.statusCode < 500);
  });
  req.on('error', () => retry());
  req.on('timeout', () => { req.destroy(); retry(); });
  function retry() {
    if (tries > 100) { cb(false); return; } // ~60s max
    setTimeout(() => waitForServer(cb, tries + 1), 600);
  }
}

function createWindow() {
  win = new BrowserWindow({
    width: 1440,
    height: 900,
    backgroundColor: '#08090a',
    title: 'joulectrl',
    autoHideMenuBar: true,
    webPreferences: { contextIsolation: true, nodeIntegration: false },
  });
  Menu.setApplicationMenu(null);
  win.loadURL(`http://127.0.0.1:${PORT}/`);
}

app.whenReady().then(() => {
  startServer();
  waitForServer((ok) => {
    if (!ok) {
      console.error('API server did not come up');
      app.quit();
      return;
    }
    createWindow();
    win.on('closed', () => { win = null; });
  });
});

app.on('before-quit', () => { app.isQuitting = true; });
app.on('window-all-closed', () => app.quit());
app.on('quit', () => {
  if (!serverProc) return;
  if (isWindows) {
    // serverProc.kill() only kills the launcher wrapper on Windows — tree-kill uvicorn.
    spawn('taskkill', ['/PID', String(serverProc.pid), '/T', '/F'], { windowsHide: true });
  } else {
    serverProc.kill('SIGTERM');
  }
});
