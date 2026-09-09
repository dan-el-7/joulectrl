# Desktop app (Electron wrapper)

`npm run desktop` (or `frontend/desktop.bat` on Windows) starts the joulectrl
dashboard as a standalone desktop application:

- spawns `uvicorn api.app:app` as a child process (repo root as cwd),
- waits for the API health endpoint, then opens an Electron window on
  `http://127.0.0.1:<port>/`,
- tree-kills the API child when the window closes (taskkill /T on Windows,
  SIGTERM elsewhere).

## Environment overrides

| Variable | Default | Meaning |
|---|---|---|
| `JOLECTRL_PORT` | `8127` | API port |
| `JOUCTRL_PYTHON` | `C:/Users/Subhrajyoti/.venvs/joulectrl/Scripts/python.exe` | interpreter with fastapi/uvicorn |

## Notes

- Requires `node`/`npm` and `npm install` (electron devDependency).
- On the measurement machine, override `JOUCTRL_PYTHON` to that machine's
  interpreter; everything else is machine-agnostic.
- Electron is pinned to `40.10.2` (binary cached locally during development;
  any recent version works — the main process uses only stable APIs).
