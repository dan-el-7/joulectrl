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

- **Done & verified:** repo dan-el-7/joulectrl bootstrapped. Hour-0 hardware checklist re-verified with root via pkexec (commit 73ed1b1): energy_uj advances (~8.6 mJ/s idle), class map even=Zen5 5.09GHz / odd=Zen5c 3.51GHz, cap honored only with boost=0 (cur_freq 1.98 GHz at 2 GHz cap vs 5.04 GHz boost=1), tuned=throughput-performance, AC=1, boot_id=6a6eb70b-267a-4ede-a0b9-b15ce2cb6fc2. energy/base.py (EnergyBackend + wrap-safe EnergyAccumulator), core/topology.py, core/discovery.py, 12 unit tests green. fixtures/real/{topology,capability_report,energy_trace_idle}.json. CI workflow on every push.
- **In flight:** adapting to B's models v0 (landed on main); then helper/ skeleton.
- **Resume here:** `cd ~/joulectrl-a && git pull --rebase origin main && .venv/bin/python -m pytest tests/unit -q` — then write helper/ skeleton: docs/HELPER.md + op set (begin_session, read_energy, apply_configuration, heartbeat, restore, end_session), Unix socket + peer-cred auth.
- **Gotchas:** energy reads root-only (pkexec works, GUI prompt). boost=1 makes caps silent no-ops — always (boost, cap) pairs here. policy0 scaling_min_freq=623377. Never run heavy loops while a [measuring] window is open. AGENTS2/HANDOFF edits: quote heredocs — bash eats backticks.
- **Handoffs owed / waiting on:** D's kernel [contract] line by h2 (drives C1/C2 calibration).


## Agent B — resume packet

- **Done & verified:** Gate 1 complete ([gate1]): `core/models.py` v0 (9 tests), `core/store.py` (4 tests), `energy/synthetic.py` (5 tests), `core/optimizer.py` (11 tests). 29 unit tests green.
- **In flight:** Gate 1 is now merged to `main` at `87d418a`. Implementing Gate 2 `core/runner.py` (workload execution harness, energy measurement, cancellation).
- **Resume here:** `Get-Content core/models.py, energy/synthetic.py, workloads/base.py` then create runner unit tests for successful measurement, verification failure, timeout, and process-group cancellation.
- **Gotchas:** Runner must use `taskset` for affinity on Linux, execute argument arrays directly (never shell string interpolation), and track process groups for clean cancellation.
- **Handoffs owed / waiting on:** Gate 1 complete; unblocks all downstream agents. Ready for Agent D's workload runner integration.






## Agent C — resume packet

- **Done & verified:** `docs/API.md` v1 frozen contract; FastAPI backend in `api/app.py` implementing all endpoints per PLAN §8, §6b, §6c; 13 unit tests in `tests/unit/test_api.py` green; Vite React frontend in `frontend/` (TypeScript, ParetoChart, SetupView, ExplorerView, ValidationView, WatchPanel) building cleanly to `frontend/dist`.
- **In flight:** Gate 1 complete; standing by for Gate 2 integration (runner state machine & live SSE events).
- **Resume here:** Run `npm --prefix frontend run build` and `pytest tests/unit/test_api.py`.
- **Gotchas:** Dev machine only; single origin at 127.0.0.1:8000; Windows AppControl requires running Python directly from uv python cache.
- **Handoffs owed / waiting on:** Ready to ingest live SSE events from Agent B's runner as soon as implemented.

## Agent D — resume packet

- **Done & verified:** Compute kernel `workloads/kernel/fixed_compute.c`, workload plugin contract `workloads/base.py`, reference plugin `workloads/fixed_compute.py`, clean-build plugin `workloads/clean_build.py`, synthetic fixtures `fixtures/synthetic/`, explanation layer `explain/`, integration tests `tests/integration/test_workload_lifecycle.py`. 19 tests passing.
- **In flight:** `d/integration-tests`, preparing demo assets in `demo/`.
- **Resume here:** `python -m unittest tests/integration/test_workload_lifecycle.py`
- **Gotchas:** `Store` methods are `create_experiment`, `record_run`, `save_profile`, `save_selection`, `record_calibration`.
- **Handoffs owed / waiting on:** Gate 1 complete for D. Waiting on Agent B's runner to implement plugin contract execution against the state machine.
