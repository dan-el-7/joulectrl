# joulectrl

> **Find the lowest energy needed to get the job done on time.**

Local-first Linux tool: profile a repeatable workload, measure CPU-package energy and
runtime, select the lowest-energy measured configuration within a runtime budget, and
verify that selection with fresh executions.

The optimizer is entirely deterministic. An LLM is an optional explanation interface —
not a dependency, measurement source, or CPU controller.

## Quick start

```bash
git clone https://github.com/dan-el-7/joulectrl.git && cd joulectrl
python3 -m venv .venv && .venv/bin/pip install -e .[dev]
.venv/bin/python -m pytest tests/unit -q        # all green = healthy clone
```

## Privileged helper (required for energy reads on root-only-counter machines)

The root helper does ALL privileged work (energy reads, cap/boost writes, restore)
over a local Unix socket — the app never runs as root.

```bash
# one pkexec prompt at launch; ops after that are prompt-free
pkexec $PWD/helper/daemon.py
# check it's alive:
python3 -m helper.client read_energy   # {"ok": true, "uj": ...}
```

Ops: `begin_session, read_energy, apply_configuration, heartbeat, restore, end_session`
(full contract: `docs/HELPER.md`). It snapshots all settings before any change and
auto-restores if the client dies (30 s watchdog). If anything ever goes wrong:
`python3 -m helper.client restore`.

## CLI

```bash
joulectrl layouts                # execution-layout validation points from the class map
joulectrl check-calibration      # sanity cross-check on calibration fixtures
joulectrl run-fixed --workers 4  # measure the approved fixed-compute workload
```

(Same as `python3 -m cli.main <cmd>` if not installed.)

## Dashboard

```bash
.venv/bin/uvicorn api.app:app --host 127.0.0.1 --port 8000
# frontend (dev): cd frontend && npm run dev   -> http://localhost:5173
```

Binds 127.0.0.1 only. Remote access via SSH tunnel (`ssh -L 8000:127.0.0.1:8000`).
Route table: `docs/API.md`.

## What the measurements mean

- The metric is **hardware-reported CPU-package energy** (powercap sysfs), not
  wall-outlet power, GPU power, or estimates. Missing energy is never reported as zero.
- Every experiment restores all touched CPU settings (verified readback).
- Selection claims are bounded: *"lowest-energy measured configuration meeting your
  runtime rule"* — never "guaranteed optimal".

## Repo map

- Product/technical spec: `docs/PLAN.md` · Team coordination: `docs/TEAM_PLAN.md`
- Agent contract (binding): `AGENTS.md` · live state: `AGENTS2.md` · resume packets: `HANDOFF.md`
- Pre-verified demo-laptop hardware facts: `docs/VERIFIED_DEMO_LAPTOP.md`
- Real machine measurements: `fixtures/real/` (topology, capability report, C1/C2
  calibration, energy trace, controls re-verification)
- Helper contract: `docs/HELPER.md` · API contract: `docs/API.md`

## License

MIT — see `LICENSE`.
