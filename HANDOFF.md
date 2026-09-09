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

- **Done & verified:** repo bootstrapped; hour-0 checklist re-verified; energy/base.py + topology/discovery + fixtures + CI (73ed1b1); helper daemon unit (48e555e: apply/restore zero-mismatch live, watchdog, out-of-range rejection, 29 tests green); C1 calibration committed — fixtures/real/calibration_c1.json (fast 8.467s/74.99J/8.86W, efficient 12.280s/79.08J/6.44W, class map confirmed 1.45x). MACHINE FACTS: boost=0 clamps cpuinfo_max to 2.0 GHz both classes; amd-pstate readback async (retry needed); helper socket /run/joulectrl-helper.sock (passwordless pkexec via /etc/polkit-1/rules.d/49-joulectrl-helper.rules).
- **In flight:** none — C1 unit closed.
- **Resume here:** `cd ~/joulectrl-a && git pull --rebase origin main` — then write core/run_c2.py: C2 dense sweep (stock row first for scaling efficiency, then N cap points 623377..2000000 kHz boost=0 per class, 4 workers one SMT sibling each: fast layout CPUs [0,2,4,6], efficient [1,3,5,7]); bracket with [measuring] lines; commit fixtures/real/calibration_c2.json.
- **Gotchas:** kernel point size: C2 should use chunks=32768 iters=200000 (~2x C1 work per worker? verify empirically — target 8-15s per point). Energy brackets run (e1 before launch, e2 after termination). run_c1.py's chunks/s parser fixed (value in parens). Helper daemon may need restart if machine rebooted: `pkexec /home/dan-el/joulectrl-a/helper/daemon.py` (passwordless).
- **Handoffs owed / waiting on:** none open; C2 next. B's runner/CLI/watch landing — A co-signs watch baseline semantics on real hardware when B's detector is ready.


## Agent B — resume packet

- **Done & verified:** Gate 1 complete ([gate1]): `core/models.py` v0 (9 tests), `core/store.py` (4 tests), `energy/synthetic.py` (5 tests), 29 unit tests green. `core/runner.py`, `core/experiment.py`, `core/watch.py`, and `core/validation.py` cover measurement, cancellation, lifecycle, watch detection, restoration failure, and fresh validation. `cli/main.py run-fixed` uses only the approved fixed workload and helper operations. Bundled Python compile/smoke passes; `tests.integration.test_watch_mode` passes 4/4.
- **In flight:** None; synthetic unavailable-counter clock regression is fixed and pushed with a regression test.
- **Resume here:** `git status --short; git pull --rebase origin main` then inspect C's validation/watch endpoint integration.
- **Gotchas:** Runner uses `taskset --cpu-list` only on Linux, executes argument arrays directly (never shell string interpolation), and terminates POSIX process groups. This clone has no `python`, `py`, project venv, or pytest; bundled Python is `C:\Users\trive\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe` but has no pytest.
- **Handoffs owed / waiting on:** Gate 1 complete; unblocks all downstream agents. Ready for Agent D's workload runner integration.






## Agent C — resume packet

- **Done & verified:** `docs/API.md` v1 frozen contract; FastAPI backend in `api/app.py` implementing all endpoints per PLAN §8, §6b, §6c; 13 unit tests in `tests/unit/test_api.py` green; Vite React frontend in `frontend/` (TypeScript, ParetoChart, SetupView, ExplorerView, ValidationView, WatchPanel) building cleanly to `frontend/dist`. Re-verified after pull 8b5b999: `npm --prefix frontend run build` green, 13/13 api tests green.
- **In flight:** Gate 2: serve B's `core/store.py` + D's synthetic fixtures (`fixtures/synthetic/*.json`) through the API; render D's `explain/` templates + restore status in ValidationView.
- **Resume here:** Read `api/app.py` + `explain/templates.py`, then extend the API to serve `fixtures/synthetic/` data end-to-end.
- **Gotchas:** Dev machine only; single origin at 127.0.0.1:8000; Windows: `python`/`py` are NOT on PATH — use `"$APPDATA/uv/python/cpython-3.14-windows-x86_64-none/python.exe"` (Roaming, not Local AppData). Store methods are `create_experiment, record_run, save_profile, save_selection, record_calibration`.
- **Handoffs owed / waiting on:** Waiting on B's runner + SSE event wiring for live experiment events; A's helper restore path for restore-status endpoint.

## Agent D — resume packet

- **Done & verified:** Gate 4 exit met ([gate4]): Compute kernel `workloads/kernel/fixed_compute.c`, workload plugins `clean_build` & `fixed_compute` with presets & registry, explanation layer `explain/` with deterministic templates & local LLM mock verification, 3 fresh validation pairs with drift check and JSON export verification in `tests/integration/test_validation_export.py`, passive watch-mode auto-detection integration in `tests/integration/test_watch_mode.py`, and interactive demo script with watch mode in `demo/run_demo.py`. 37 tests passing (100% green).
- **In flight:** Complete through Gate 4. Standing by for cross-agent integration and live demonstration execution.
- **Resume here:** `python -m unittest discover -s tests -p "test_*.py"` or run full suite via `python demo/run_demo.py`
- **Gotchas:** Terminal output on Windows cp1252 consoles cannot encode unicode mathematical symbols like ≤ / ≥ — use ASCII <= and >= in all explanation strings. In `energy/synthetic.py` advance_uj returns before updating simulated time when energy is unavailable.
- **Handoffs owed / waiting on:** Gate 4 deliverables complete (`[gate4]` posted). Ready for live demo on Fedora demo laptop.
