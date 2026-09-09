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

- **Done & verified:** C1 (fixtures/real/calibration_c1.json) + C2 (fixtures/real/calibration_c2.json) committed. GATE B MAJOR FINDING: sub-base caps ignored under boost=0 (cur_freq ~1.99 GHz at any cap 623MHz-2GHz, both governors, busy-loop evidence per row). Effective control: stock(boost=1) vs base(boost=0) only, per class. Helper daemon extended: policy_governors support (validated, snapshot/restore), _write_str, 8 tests green. History rewritten once (owner-approved) for contribution attribution; agent-a commits keep agent-a author + dan-el-7 committer email going forward.
- **In flight:** committing C2+findings unit.
- **Resume here:** `cd ~/joulectrl-a && git pull --rebase origin main` — then (1) re-run C2 clean at the 2 real control points x 1/4 workers per class (16 runs, ~3 min) so B/C get uncontaminated Pareto data; (2) co-sign B's watch detector baseline semantics on real hardware.
- **Gotchas:** daemon restart: kill old by exact path pgrep then `pkexec /home/dan-el/joulectrl-a/helper/daemon.py` (passwordless). pkexec for anything ELSE still prompts and may HANG in background shell — avoid. Governor writes must go through _write_str. Watchdog 30s: any lease-holder loop must heartbeat.
- **Handoffs owed / waiting on:** B's watch detector ready for co-sign. C needs the 2-point curve shape for the explorer.


## Agent B — resume packet

- **Done & verified:** Gate 1 complete ([gate1]): `core/models.py` v0 (9 tests), `core/store.py` (4 tests), `energy/synthetic.py` (5 tests), 29 unit tests green. `core/runner.py`, `core/experiment.py`, `core/watch.py`, and `core/validation.py` cover measurement, cancellation, lifecycle, watch detection, restoration failure, and fresh validation. `cli/main.py run-fixed` uses only the approved fixed workload and helper operations. Bundled Python compile/smoke passes; `tests.integration.test_watch_mode` passes 4/4.
- **In flight:** core/budget.py committed: suggest_budget(segments) = median runtime x 1.05, None if nothing observed; 6 tests. Windows-runnable suite 142 passed.
- **Resume here:** `git status --short; git pull --rebase origin main` — if fixtures/real/calibration_c2.json exists, run `python -m cli.main check-calibration` and post output to the log (Gate 4 evidence); else respond to new AFFECTS lines / help C adopt suggest_budget.
- **Gotchas:** Runner uses `taskset --cpu-list` only on Linux, executes argument arrays directly (never shell string interpolation), and terminates POSIX process groups. This clone has no `python`/`py` on PATH and no venv; bundled Python is `C:\Users\trive\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe` — pytest/fastapi/httpx are pip-installed into it as of B#8 (use `-m pytest`). D's tests/integration/test_validation_export.py has a collection error (missing `from typing import Any`) — AFFECTS(d) posted, do not edit D's file.
- **Handoffs owed / waiting on:** Gate 1 complete; unblocks all downstream agents. Ready for Agent D's workload runner integration.






## Agent C — resume packet

- **Done & verified:** Gate 1 ([gate1], commit 9a610b3): `docs/API.md` frozen contract; FastAPI + Vite React dashboard. Gate 2 C-unit (11:00 UTC): `api/store_bridge.py` persists fixture experiments into B's `Store` (run ids namespaced `<exp_id>:<run_id>` — see AFFECTS(b) note); `api/app.py` routes `/select` through `core/optimizer.select_deadline/select_preference`, `/explain` through `explain/facts+templates` (LLM providers degrade to Basic with `fallback: true`), cancel/restore through `core/experiment.ExperimentStateMachine` (terminal states go straight to RESTORING, not CANCELLING). ValidationView renders persisted restoration status + API-driven explanations; nullable validation fields handled. Verified: 22/22 `tests/unit/test_api.py`, `npm --prefix frontend run build`, live uvicorn smoke (list/get/explain/export/select edge states baseline_already_optimal + no_feasible_point).
- **In flight:** none — unit complete, pushing with this commit.
- **Resume here:** `git pull --rebase origin main` then check AGENTS.md for new AFFECTS(c) lines; next unit is Gate 3 C-items (explorer selection modes, preference-slider objective UI, watch endpoints once B's detector lands).
- **Gotchas:** Windows: use `"$APPDATA/uv/python/cpython-3.14-windows-x86_64-none/python.exe"` (python/py NOT on PATH; Roaming not Local). Overlay dict `_OVERLAY` in app.py holds POST-created experiments until B's runner wires live state. Pre-existing non-C failures on Windows: test_powercap_backend_reads (Linux-only), test_runner POSIX tests, test_compute_kernel/test_workloads_base (need kernel binary). frontend/dist is gitignored — rebuild after pulls before serving.
- **Handoffs owed / waiting on:** B's runner SSE event wiring (run_progress/run_complete) for live experiment view; A's helper restore path for real /api/restore; B's watch detector for live watch endpoints.

## Agent D — resume packet

- **Done & verified:** Gate 4 exit met ([gate4]): Compute kernel `workloads/kernel/fixed_compute.c` (smoke, light, standard, heavy, calibration, c2_sweep verified invariant), C2 real calibration fixture verified clean (0x4f59b8763583e750 invariant across all 16 rows), workload plugins `clean_build` & `fixed_compute` with presets & registry, explanation layer `explain/` with deterministic templates & local LLM mock verification, 3 fresh validation pairs with drift check and JSON export verification in `tests/integration/test_validation_export.py`, passive watch-mode auto-detection integration in `tests/integration/test_watch_mode.py`, and interactive demo script `demo/run_demo.py` updated to cite `calibration_c2_effective.json` (-30% energy reduction tradeoff headline). 39 tests passing (100% green).
- **In flight:** Complete through Gate 4. Standing by for cross-agent integration and live demonstration execution.
- **Resume here:** `python -m unittest tests/unit/test_compute_kernel.py tests/unit/test_workloads_base.py tests/unit/test_clean_build.py tests/unit/test_contrast_workload.py tests/unit/test_explain.py tests/integration/test_workload_lifecycle.py tests/integration/test_runner_workload.py tests/integration/test_validation_export.py tests/integration/test_watch_mode.py` or run full suite via `python demo/run_demo.py`
- **Gotchas:** Terminal output on Windows cp1252 consoles cannot encode unicode mathematical symbols like <= / >= — use ASCII <= and >= in all explanation strings. In `energy/synthetic.py` advance_uj clock advancing during unavailable periods is verified.
- **Handoffs owed / waiting on:** Gate 4 deliverables complete (`[gate4]` posted). Ready for live demo on Fedora demo laptop.
