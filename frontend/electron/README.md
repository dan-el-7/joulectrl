# Desktop app (Electron wrapper)

`npm run desktop` — or `frontend/desktop.sh` (Linux/macOS) / `frontend/desktop.bat`
(Windows) — starts the joulectrl dashboard as a standalone desktop application:

- discovers a Python interpreter (below), then spawns
  `uvicorn api.app:app` as a child process (repo root as cwd),
- waits for the API health endpoint, then opens an Electron window on
  `http://127.0.0.1:<port>/`,
- tree-kills the API child when the window closes (taskkill /T on Windows,
  SIGTERM elsewhere).

## Environment overrides

| Variable | Default | Meaning |
|---|---|---|
| `JOLECTRL_PORT` | `8127` | API port |
| `JOUCTRL_PYTHON` | _(discovery)_ | interpreter with fastapi/uvicorn installed |

## Python discovery (machine-agnostic, nothing hardcoded)

1. `JOUCTRL_PYTHON` env var, if set;
2. `<repo>/.venv` then `<repo>/venv` (Scripts/python.exe on Windows, bin/python elsewhere);
3. `python3` (or `python` on Windows) from `PATH`.

## Notes

- Requires `node`/`npm` and `npm install` (electron devDependency).
- The repo must be installed into the chosen interpreter
  (`pip install -e .` plus fastapi/uvicorn) — the same requirement as the
  server mode.
- Electron is pinned to `40.10.2` (binary cached locally during development;
  any recent version works — the main process uses only stable APIs).
