# HANDOFF.md — per-agent resume packets (model-failure insurance)

Every agent maintains a resume packet for its own letter, written **as if the reader is a
brand-new model with zero context**: if your session dies mid-unit, your successor (or a
rescuer) reads this file plus `AGENTS2.md` and continues from your exact stopping point instead
of losing the hour.

Companion files: `AGENTS.md` (process contract), `AGENTS2.md` (live state board). This file is
**rewritable** per section (same ownership rules as AGENTS2.md: rewrite your own section only,
pull --rebase before editing, push immediately after).

## Update triggers

- **Before starting any in-flight work** — a packet must exist before there is anything to lose.
- **After every commit/push** — refresh "done & verified" and "resume here".
- **On any error or blocked state that could kill the session** — write the packet FIRST, then
  debug. If you only have 30 seconds before dying, spend them here and on AGENTS2.md's heartbeat.
- **When ending a session** (even a clean one).
- The packet is allowed to be slightly stale about trivia, but "in flight" and "resume here"
  must never be.

## Rules

1. One section per letter; rewrite your own, never others'. A rescuer marks edits
   `[rescued-by <letter>]`.
2. Commit hashes and file paths over prose — they survive context loss; adjectives don't.
3. "Resume here" must be **one concrete, runnable step** (a command, a file to open, a test to
   run), not a description of a step.
4. If your clone has uncommitted WIP, say so explicitly in "in flight" with the exact
   `git status` / `git stash list` state, so the successor can salvage or discard deliberately.

## Resume protocol (for the successor session — also referenced as AGENTS.md §4b)

1. `git pull --rebase origin main`.
2. Read **your** section below + your AGENTS2.md live state + the last lines of your AGENTS.md §8 log.
3. Inspect the clone: `git status`, `git stash list`, `git log --oneline -10`, open branches.
   Decide salvage: commit WIP as `[wip]` if it passes its tests, else stash with a note here.
4. Increment your session generation in AGENTS2.md, post a fresh heartbeat, set status `active`.
5. Execute the "resume here" line. Finish the open unit before starting anything new (§0.6).
6. If the packet is missing or stale: fall back to your gate checklist (AGENTS.md §7) + the git
   history of your owned files. Post what you reconstructed in "done & verified" so the next
   failure isn't twice as costly.

---

## Agent A — resume packet

- **Done & verified:** repo bootstrapped; hour-0 hardware checklist re-verified (energy advances, class map, boost=0 cap honored, tuned/AC). energy/base.py + core/topology.py + core/discovery.py + fixtures/real/*.json + CI (commit 73ed1b1). Helper daemon unit complete: helper/daemon.py + helper/client.py + docs/HELPER.md + 8 tests (29 total green); verified live on this machine — apply/restore cycle zero-mismatch, out-of-range rejection, watchdog. MACHINE FACT: boost=0 clamps cpuinfo_max_freq to 2.0 GHz both classes; cap ladder 623377..2000000 kHz.
- **In flight:** none — unit closed. (Committing now.)
- **Resume here:** `cd ~/joulectrl-a && git pull --rebase origin main && .venv/bin/python -m pytest tests/unit -q` — then update fixtures/real/capability_report.json with the boost=0 cpuinfo-clamp fact + calib ladder, and wait on D's kernel for C1.
- **Gotchas:** helper daemon must run as root: `pkexec /home/dan-el/joulectrl-a/helper/daemon.py` (polkit rule /etc/polkit-1/rules.d/49-joulectrl-helper.rules makes it passwordless; daemon has shebang, executable). Old daemon instances: kill by pgrep 'venv/bin/python3.*helper/daemon.py'. restore must write boost BEFORE caps (cpuinfo clamp). amd-pstate readback is async — _read_int_retry handles it. systemd-inhibit running (sleep blocked) for the session; dies on reboot (intended).
- **Handoffs owed / waiting on:** D's kernel [contract] line (C1/C2 calibration driver). B: models v0 adopted for CapabilityReport-shaped output next.


## Agent B — resume packet

- **Done & verified:** Gate 1 complete ([gate1]): `core/models.py` v0 (9 tests), `core/store.py` (4 tests), `energy/synthetic.py` (5 tests), 29 unit tests green. `core/runner.py`, `core/experiment.py`, and focused tests cover measurement, cancellation, legal lifecycle, restoration failure, and profile-point integration. `cli/main.py run-fixed` now uses only the approved fixed workload and helper operations, persists the run, and restores in `finally`. Compile/help smoke pass.
- **In flight:** None; CLI unit is committed locally next, with Linux helper-backed run pending demo hardware execution.
- **Resume here:** `git status --short; git pull --rebase origin main` then run `python -m cli.main run-fixed --help` or execute on the demo Linux laptop with the helper daemon.
- **Gotchas:** Runner uses `taskset --cpu-list` only on Linux, executes argument arrays directly (never shell string interpolation), and terminates POSIX process groups. This clone has no `python`, `py`, project venv, or pytest; bundled Python is `C:\Users\trive\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe` but has no pytest.
- **Handoffs owed / waiting on:** Gate 1 complete; unblocks all downstream agents. Ready for Agent D's workload runner integration.






## Agent C — resume packet

- **Done & verified:** `docs/API.md` v1 frozen contract; FastAPI backend in `api/app.py` implementing all endpoints per PLAN §8, §6b, §6c; 13 unit tests in `tests/unit/test_api.py` green; Vite React frontend in `frontend/` (TypeScript, ParetoChart, SetupView, ExplorerView, ValidationView, WatchPanel) building cleanly to `frontend/dist`. Re-verified after pull 8b5b999: `npm --prefix frontend run build` green, 13/13 api tests green.
- **In flight:** Gate 2: serve B's `core/store.py` + D's synthetic fixtures (`fixtures/synthetic/*.json`) through the API; render D's `explain/` templates + restore status in ValidationView.
- **Resume here:** Read `api/app.py` + `explain/templates.py`, then extend the API to serve `fixtures/synthetic/` data end-to-end.
- **Gotchas:** Dev machine only; single origin at 127.0.0.1:8000; Windows: `python`/`py` are NOT on PATH — use `"$APPDATA/uv/python/cpython-3.14-windows-x86_64-none/python.exe"` (Roaming, not Local AppData). Store methods are `create_experiment, record_run, save_profile, save_selection, record_calibration`.
- **Handoffs owed / waiting on:** Waiting on B's runner + SSE event wiring for live experiment events; A's helper restore path for restore-status endpoint.

## Agent D — resume packet

- **Done & verified:** Compute kernel `workloads/kernel/fixed_compute.c`, workload plugin contract `workloads/base.py`, reference plugin `workloads/fixed_compute.py`, clean-build plugin `workloads/clean_build.py`, synthetic fixtures `fixtures/synthetic/`, explanation layer `explain/`, integration tests `tests/integration/test_workload_lifecycle.py`, demo script `demo/run_demo.py`, and runner workload integration `tests/integration/test_runner_workload.py`. 23 tests passing.
- **In flight:** Gate 3 preparation: contrast workload variations and preference-mode template extensions.
- **Resume here:** `python -m unittest tests/integration/test_runner_workload.py`
- **Gotchas:** `WorkloadRunner` requires `RunContext` initialized and `workload.prepare()` invoked outside measurement window.
- **Handoffs owed / waiting on:** Gate 2 exit met for Agent D (`[gate2]` posted). Unblocked cross-cutting validation.
