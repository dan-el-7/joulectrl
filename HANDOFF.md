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

## Agent A — resume packet (A#2 clean shutdown 2026-09-09T14:22:07Z — Antigravity successor: start here)

- **Done & verified (A#2 session):** (1) doctor_report() sys.platform-guard for helper probe (B's CLI workaround now optional); (2) CI fixed green 3-layer (fastapi/httpx install, python -m pytest, hardware-bound tests CI-safe via real tmp_path fake-sysfs + boot_id gate); (3) scripts/launch_dashboard.sh committed + verified E2E (venv → pkexec helper if down → npm build if missing → uvicorn 127.0.0.1:8000 → xdg-open; UI 200, real capabilities, /docs 200); (4) all-cores C2 calibration fixtures/real/calibration_c2_allcores.json (all8/all16 x stock/base x 3 reps, checksum-invariant, clean restore) + core/run_c2_allcores.py — answers C's 13:42Z question. ALL A gates [gate0]-[gate4] complete; 170 unit tests green locally.
- **Key results for demo:** canonical fixture = fixtures/real/calibration_c2_effective.json (fast/base/w4: -30% energy at 2.55x runtime). All-cores: all8 base -52% energy at 1.92x runtime vs stock; all16 STRICTLY DOMINATED by all8 (SMT adds nothing for fixed_compute — UI must show all8 as best all-cores point, all16 as caveat). Control space is genuinely 2 pts/class (stock/base, Gate B) — present as measured reality, not missing data.
- **In flight:** NONE. No [measuring] window open. Machine left in STOCK state (verify: boost=1, p0=5090000, p1=3506494).
- **Resume here:** (a) `cd ~/joulectrl-a && git pull --rebase origin main`, re-read AGENTS.md §8/§9 tail + AGENTS2.md; (b) verify machine: helper read_energy OK, stock freqs, `AC=1`, `systemd-inhibit --list | grep joulectrl` (re-run sleep-inhibit cmd in SESSION_START_A.md §"Current machine state" if absent — dies on reboot); (c) run `core/reverify_controls.py` ~30 min before demo, commit fresh controls_reverify.json; (d) tagged release via `~/.local/bin/gh release create` once API/CLI surface settles; then post your own heartbeat/off.
- **Gotchas (bit A#1/A#2, do not repeat):** quote heredocs with backticks; pkexec ONLY for helper/daemon.py (exact path — polkit rule); pkill patterns can match own shell; long loops MUST c.heartbeat() (30 s watchdog); restore to TRUE stock between classes; bracket energy reads around runs; `pip install` commands get misdetected as servers by this sandbox — run them backgrounded or via execute_code.
- **Handoffs owed / waiting on:** B parked (wake via human only). D shut down clean (99692ec). C active-idle on autonomous poll mode. AFFECTS(c) 04672ee follow-up CLOSED (C integrated + browser-verified).
- **⚠ CI RED on main as of this handoff:** C's 7afcb52 broke tests/unit/test_api.py::test_capabilities — it asserts `energy.available is True`, but C's live-first discovery reports live on CI runners (no RAPL/helper → False). C's test + C's commit → C owns the fix (likely: assert fixture-fallback shape when live unavailable, or gate on live source flag). AFFECTS(c) line for this is already drafted in the AGENTS.md log below — I did NOT push it as a separate line; C's poll will see it here. Do NOT "fix" by touching api/ or tests (not A's files).

## Agent B — resume packet

- **Done & verified:** Gate 1 complete ([gate1]): `core/models.py` v0 (9 tests), `core/store.py` (4 tests), `energy/synthetic.py` (5 tests), 29 unit tests green. `core/runner.py`, `core/experiment.py`, `core/watch.py`, and `core/validation.py` cover measurement, cancellation, lifecycle, watch detection, restoration failure, and fresh validation. `cli/main.py run-fixed` uses only the approved fixed workload and helper operations. Bundled Python compile/smoke passes; `tests.integration.test_watch_mode` passes 4/4.
- **In flight:** core/budget.py committed: suggest_budget(segments) = median runtime x 1.05, None if nothing observed; 6 tests. Windows-runnable suite 142 passed.
- **Resume here:** `git status --short; git pull --rebase origin main` — if fixtures/real/calibration_c2.json exists, run `python -m cli.main check-calibration` and post output to the log (Gate 4 evidence); else respond to new AFFECTS lines / help C adopt suggest_budget.
- **Gotchas:** Runner uses `taskset --cpu-list` only on Linux, executes argument arrays directly (never shell string interpolation), and terminates POSIX process groups. This clone has no `python`/`py` on PATH and no venv; bundled Python is `C:\Users\trive\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe` — pytest/fastapi/httpx are pip-installed into it as of B#8 (use `-m pytest`). D's tests/integration/test_validation_export.py has a collection error (missing `from typing import Any`) — AFFECTS(d) posted, do not edit D's file.
- **Handoffs owed / waiting on:** Gate 1 complete; unblocks all downstream agents. Ready for Agent D's workload runner integration.






## Agent C — resume packet

- **Done & verified:**
  - Gate 1 (commit 9a610b3): `docs/API.md` frozen contract; FastAPI + Vite React dashboard end-to-end.
  - Gate 2 (11:00 UTC): Store-backed API (`api/store_bridge.py`), `/select` → B's optimizer, `/explain` → D's templates, persisted restoration status. 22 tests.
  - **Gate 3 (commit 8ae20ba, 12:15 UTC) [contract]:** (1) SSE `/api/experiments/{id}/events` streams B's EventBus (`core/events.py`) — replay(0) burst + live subscribe, replay→subscribe race closed by re-reading after subscribe; fixture experiments get a terminal burst labeled `source:"replayed_from_store"`; `/select` publishes `selection_updated` on the bus. (2) Watch endpoints live on B's `WatchDetector` (`core/watch.py`): real `PowercapBackend` via A's discovery when readable, else B's synthetic scripted profile (accelerated ~30× on dev machines, `WatchService.DEV_TIME_SCALE`); `/api/watch/events` SSE emits `watch_sample`/`watch_state`/`watch_segment`; segment frame carries BOTH `onset_ts`/`end_ts` (SSE shape §4.2) and `onset_timestamp`/`end_timestamp` (REST shape §3.9). (3) NEW `GET /api/experiments/{id}/validation-points` (additive, in docs/API.md §2 table): B's `layout_configurations(class_map)` + measured `CalibrationRecord` points; class map from `fixtures/real/topology.json` via `_fixture_class_map()` in app.py. Verified: 28/28 `tests/unit/test_api.py`, `npm run build` clean, live uvicorn TCP smoke (full watch cycle: 120 samples → 1 segment 49.0s/2174J; SSE replay + live publish; validation-points lists layout_A/D/B/C + cal points).
  - **WIP pushed (commit 8aaa303, ~12:35 UTC):** Linear-inspired design system `frontend/src/design.ts` (near-black surfaces `#08090a/#0f1011/#141516`, Inter + `cv01/ss03`, single indigo accent `#7170ff`, semi-transparent white borders, JetBrains Mono for measured values); new `CalibrationView.tsx` (C1 single-core reference cards per class + C2 perf/W scatter per class with hover readout + scaling-efficiency cards + fast/efficient class toggle chips); `GET /api/calibration` endpoint aggregating A's `fixtures/real/calibration_c1.json` + `calibration_c2_effective.json` into per-class medians (watts, throughput, perf/W, scaling efficiency); Navbar restyled with new tab set (Setup|Profile|Calibration|Validation|Watch); index.css + index.html (Google Fonts Inter/JetBrains Mono); ALL other components color-remapped to tokens (mechanical sed: old tailwind hexes → design tokens). Build passes; `tests/unit/test_api.py` 28/28 still green.
- **In flight:** none — user asks 1 and 2 complete (C#4):
  - **Ask 1 visual pass (commit 8dedd9b):** all 5 tabs browser-verified via Chrome CDP (no clipping/overflow, zero-size controls, console errors); CalibrationView hover readouts + class toggles verified (16→8 points); live watch cycle exercised (baseline 10.0 W learned, seg_01 detected, sparkline rendered); 'cpu 1 core' wart fixed (real cpu ids from /api/calibration); ALL raw hex colors in ExplorerView/SetupView/ValidationView/WatchPanel/ParetoChart converted to design.ts tokens (scripts/tokenize_colors.py).
  - **Ask 2 desktop exec (commit e28a390):** Electron wrapper `frontend/electron/main.cjs` + `npm run desktop` + `frontend/desktop.bat`. Spawns uvicorn child (JOUCTRL_PYTHON/JOLECTRL_PORT env overrides), health-waits, opens window; window close tree-kills API (taskkill /T on Windows). Verified live. Electron pinned 40.10.2 (cache).
- **Resume here:** user ask 3 — autonomous repo-poll mode is the current activity: loop {git pull --rebase origin main; read new AGENTS.md/AGENTS2.md/HANDOFF deltas; act on AFFECTS(c)/[contract]/gate+polish items in my ownership; refresh heartbeat ≤15 min}. If session dies mid-poll, successor re-enters the same loop.
- **Gotchas:**
  - Windows venv: `C:/Users/Subhrajyoti/.venvs/joulectrl/Scripts/python.exe` (python/py NOT on PATH; system python is 3.11 without fastapi).
  - TestClient/httpx on this stack BUFFERS infinite SSE streams — `iter_lines`/`iter_bytes` hang until stream end. Test SSE at generator level (see `test_sse_replays_live_bus_history`) or over TCP with curl. Documented in test docstrings.
  - `frontend/dist` is gitignored — rebuild after pulls before serving.
  - Ports 8123–8126 may hold orphaned uvicorn processes from this session (PIDs in netstat); kill before binding, or use a fresh port.
  - A force-pushed main once (~11:40 UTC, owner-approved commit re-attribution — announced in A's log). If pull says "forced update": stash, `git fetch && git reset --hard origin/main`, pop stash, resolve.
  - Watch on dev machine always falls back to synthetic scripted profile (no readable powercap on Windows) — source is labeled in every response; that's by design, don't "fix" it.
  - The `CalibrationView` has a small known wart: C1 card shows literal text "cpu 1 core" placeholder in the corner (cosmetic, fix during visual pass).
- **User's outstanding asks (from the human directing this laptop, in order):**
  1. **Finish the visual pass** on the redesign (see In flight) — user wants "tool-grade, clean, not AI slop"; Linear-inspired tokens are in `frontend/src/design.ts`, use them everywhere.
  2. **Standalone desktop exec** — "a proper exec aside the server host": package the dashboard as a desktop app (user said "app... like a proper exec"). Approach: Electron or Tauri wrapper in `frontend/` that spawns the uvicorn API as a child process and opens a window (or simpler: a single .bat/.exe launcher that starts uvicorn + opens browser — decide based on what's installable offline; npm registry IS reachable). MUST stay within my ownership (`api/`, `frontend/`) — a launcher script inside `frontend/` is fine.
  3. **Autonomous operation** — after the above: work autonomously, sleeping between random-interval repo pulls, reading AGENTS.md/AGENTS2.md/HANDOFF.md deltas, and executing new Gate/polish items as they land from A/B/D (this is the standing instruction from the user: "work autonomously and sleep pulling the repo at random to get the status and instructions"). Keep heartbeats current per AGENTS2.md rules while doing this.
- **Handoffs owed / waiting on:** none blocking. B's runner live-run wiring will later replace the `_OVERLAY` fixture experiments in app.py (my code is ready — SSE + store both handle it). A's real-machine watch co-sign already landed (32da871).

## Agent D — resume packet

- **Done & verified:** Gate 4 exit met ([gate4]): All D deliverables complete and merged. Compute kernel `workloads/kernel/fixed_compute.c` (smoke, light, standard, heavy, calibration, c2_sweep verified invariant), C2 real calibration fixture verified clean (0x4f59b8763583e750 invariant across all 16 rows), workload plugins `clean_build` & `fixed_compute` with presets & registry, explanation layer `explain/` with deterministic templates & local LLM mock verification, 3 fresh validation pairs with drift check and JSON export verification, passive watch-mode auto-detection integration, interactive demo script `demo/run_demo.py` citing `calibration_c2_effective.json` (-30% energy reduction headline) and `controls_reverify.json` (pre-demo check PASS), `demo/README.md` documentation updated, and `SESSION_START_D.md` onboarding brief committed. 39/39 tests passing.
- **In flight:** Nothing. Session ended cleanly per A's conclusion plan (a2cdcd1).
- **Resume here:** `python -m unittest tests/unit/test_compute_kernel.py tests/unit/test_workloads_base.py tests/unit/test_clean_build.py tests/unit/test_contrast_workload.py tests/unit/test_explain.py tests/integration/test_workload_lifecycle.py tests/integration/test_runner_workload.py tests/integration/test_validation_export.py tests/integration/test_watch_mode.py` — should be 39/39 green immediately.
- **Gotchas:** Terminal output on Windows cp1252 consoles cannot encode unicode mathematical symbols like <= / >= — use ASCII <= and >= in all explanation strings. In `energy/synthetic.py` advance_uj clock advancing during unavailable periods is verified.
- **Handoffs owed / waiting on:** None. All gate deliverables complete. Demo-ready on Fedora laptop.
