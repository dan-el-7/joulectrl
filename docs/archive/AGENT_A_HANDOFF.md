# AGENT_A_HANDOFF.md — full-context handoff to Antigravity (Sep 9, 2026, ~17:20 UTC)

Written by Agent A (session A#3) for a zero-context successor (Antigravity) taking over
iteration on this machine. Read this FIRST, then `AGENTS.md` (contract), `AGENTS2.md`
(live board), `HANDOFF.md` (per-agent packets). Repo: https://github.com/dan-el-7/joulectrl
(clone: ~/joulectrl-a, venv `.venv`, git identity `agent-a <agent-a@joulectrl.local>`).

**Scope note:** the human owner granted A#3 an exception to edit `frontend/` + `api/`
for dashboard quality + packaging (logged in AGENTS.md §8, 14:30Z line). Antigravity
inheriting this handoff inherits that exception: iterate freely on frontend/api/ and
A-owned files (helper/, core/discovery|topology|calibration, fixtures/real/, scripts/,
.github/workflows/ci.yml). B/C/D-owned files (core/models.py, core/runner.py, etc.)
still need their owners — leave AFFECTS(<letter>) notes in AGENTS.md instead.

## 1. State right now (verified at handoff)

- Machine: STOCK and clean — boost=1, policy0=5.09 GHz, amd_pstate **active**, AC on.
- Helper daemon: RUNNING (single instance, new code incl. pstate_mode knob), reachable:
  `cd ~/joulectrl-a && .venv/bin/python -m helper.client read_energy` → {"ok": true, ...}
- API server: RUNNING on http://127.0.0.1:8000 (pid in /tmp/joulectrl-api.pid; kill+restart:
  `.venv/bin/uvicorn api.app:app --host 127.0.0.1 --port 8000 &`)
- Sleep inhibitor: RUNNING (systemd-inhibit, joulectrl). Dies on reboot — re-run:
  `systemd-inhibit --what=sleep:idle:handle-lid-switch --mode=block --who=joulectrl --why="demo" sleep infinity &`
- CI: GREEN on main (latest b1cc7e2). 175 unit tests green locally (1 skip = boot_id-gated
  real-topology test on other machines — by design).
- GNOME app entry "joulectrl" installed (Electron window; `scripts/install_linux_app.sh`
  to reinstall). Browser flow: `scripts/launch_dashboard.sh`.
- **AFTER ANY REBOOT**: one command restores everything: `~/joulectrl-a/scripts/launch_dashboard.sh`
  (pkexec password prompt once for the helper; it's the only password you'll need).

## 2. What was built this session (A#3, all pushed, all co-authored dan-el-7)

1. **Frontend crash + quality fixes** (c2cf3a3): SetupView white-screen crash
   (classes shape mismatch: live API returns {cpus, hw_max_freq}, component assumed
   number[] — fixed via `classCpus()` in types.ts); 5 invalid rgba()XX colors; removed
   hardcoded fallbacks (cfg_stock_all / 44.6% / "16 threads · Stock boost"); ParetoChart
   divide-by-zero guard + honest axis label.
2. **Live experiment engine** (134f6fb, api/engine.py): REAL runs on helper machines.
   `POST /api/experiments` → background thread: begin helper session → per-config
   apply(boost[, caps][, pstate_mode]) → WorkloadRunner run (energy-bracketed) →
   restore (op_restore CLOSES the session — engine re-begins after each) →
   deterministic selection (B's optimizer: deadline|preference) → overlay update +
   SSE. Dev machines (no helper) keep the fixture path, labeled. Work size:
   **8192 chunks × 200k iters per worker** (4–11 s/point, calibration-grade — do NOT
   shrink back to smoke presets; the human explicitly wants ≥5s sustained per point).
3. **SSE progress** (contract event names!): `run_progress` / `run_complete` with
   run_index/total_runs → navbar "run N/M" progress bar in App.tsx + live explorer
   refresh. NOTE: B's EventBus validates names against EVENT_NAMES in core/events.py —
   use existing names (experiment_state, run_progress, run_complete, profile_ready,
   selection_updated, restore_status), don't invent new ones.
4. **Calibration curves** (3fee42f, 21de899): perf/W chart now maps the API's
   snake_case fields (perf_per_watt, scaling_efficiency — was camelCase = NaN =
   "random dots"); connected per-series curves; machine-fact honesty note (2-point
   control space, Gate B basis, DVFS physics cross-check in commit message).
5. **Free-form inputs + warnings** (21de899): NumField text input beside every slider
   (type any value, Enter/blur commits, no caps); honest warnings for sub-second /
   <5s / <50%-of-baseline / >1h budgets.
6. **Linux app** (bc3005f + earlier): GNOME .desktop entry + SVG icon +
   scripts/install_linux_app.sh; Electron wrapper (C's main.cjs) spawns uvicorn child,
   clean SIGTERM shutdown on window close.
7. **Experimental passive-caps dev option** (24ffd1b + b1cc7e2): amd_pstate passive
   mode makes caps bind WITH boost on (measured 3.46 GHz under 3.5 GHz cap).
   Helper control key `pstate_mode` (active|guided|passive, snapshotted+restored);
   Setup UI checkbox "Experimental: passive-mode caps" → API field
   `experimental_passive_caps` → engine per-request flag → adds boost-on capped
   ladder (4.0/3.5/3.0/2.5/2.0 GHz) on the all-physical layout. Env fallback:
   JOUCTRL_PASSIVE_CAPS=1. **Measured verdict: NOT worth it** (cap4.0G=96% energy @
   127% runtime; 3.5G=109% WORSE than stock; passive base=171% energy) — documented
   in fixtures/real/capability_report.json `pstate_mode_note`. Kept as dev option
   per owner request.
8. **CI fixes**: 3-layer fix (fastapi/httpx install, python -m pytest, CI-safe
   hardware tests — fake sysfs as real tmp file tree + boot_id gate);
   energy domain normalization (live 'package' → 'package-N' from RAPL path) which
   fixed C's red test_capabilities both locally and on runners.

## 3. Verified facts (do not re-discover; details in fixtures/real/ + AGENTS.md §9)

- **Energy counter**: powercap intel-rapl:0 root-only, wrap 65,532,610,987 uJ.
  ALL energy reads go through the helper. Demo headline: fast/base/w4 = −30% energy
  at 2.55× runtime (fixtures/real/calibration_c2_effective.json).
- **All-cores** (calibration_c2_allcores.json): all8 base = −52% energy @ 1.92×
  runtime; **all16 strictly dominated by all8** (SMT adds nothing for this kernel).
- **Control space**: 2 points/class (stock=boost on, base=boost off). Caps with
  boost=1 are accepted-but-IGNORED in active AND guided modes (verified live).
  Sub-base caps ignored under boost=0 (clamps ~1.99 GHz). EPP dead (single value).
  Passive mode is the only caps-with-boost path — see §2.7 for why it's off by default.
- **Kernel checksums**: 16384/1w = 0xc2493c07d6b29c85; 32768/4w = 0x4f59b8763583e750;
  all8 (65536) = 0x4b7ca5f1275dd718; all16 (131072) = 0x6bea2ec153929dee. Invariant
  across worker counts — use to sanity-check any new runner path.

## 4. Gotchas that bit this session (do not repeat)

- `op_restore` on the helper **closes the session** — any loop doing apply→restore
  per iteration must re-begin_session after each restore.
- Helper watchdog kills the lease after 30 s without heartbeat — long loops must
  call `c.heartbeat()` around runs.
- Stale same-user helper leases after a crashed server: engine now force-clears at
  start (`helper.end_session()` then `begin_session()`).
- npm's allowScripts blocks electron's postinstall — fix:
  `(cd frontend && node node_modules/electron/install.js)`; if dist/ is half-extracted,
  `rm -rf node_modules/electron/dist` first, and `printf 'electron' > node_modules/electron/path.txt`
  (NO trailing newline) if you extract manually.
- History was rewritten (co-author trailers added, 13d4af1 precedent + this session):
  other agents' clones may need `git pull --rebase` or re-clone.
- The Hermes terminal sandbox misdetects `pip install` / server-ish foreground commands:
  run them with background=true or via execute_code.
- pkexec ONLY for helper/daemon.py (polkit rule matches the exact path). Root work
  otherwise goes through the helper.
- Frontend bundle caching: after `npm run build`, hard-reload the browser (or check
  the served asset hash) before concluding a fix didn't work.

## 5. Known open items / next iterations (owner wants to iterate)

- **Validation runs aren't live yet**: the Validation view still uses fixture data;
  the engine does profiling+selection only. A natural next unit: engine-driven
  validation pairs (selected config + baseline, fresh runs, drift check) reusing
  `_run_one`.
- **Onboarding baseline persistence**: engine re-measures candidates per experiment
  (calibration fast-path covers all8/all16 only). Persisting a per-machine baseline
  (first-run all-physical stock measurement, reused after) is designed but not built.
- **test_capabilities flake**: passed locally+CI now, but it asserts live shape;
  if CI flakes again on runners, make it tolerate fixture-fallback energy.available=false.
- **Frontend polish backlog**: Explorer still shows fixture experiment until a live
  one completes (overlay swap design); selection cards could cite profile_source;
  calibration view could offer the passive-caps experimental points when a passive
  experiment has run.
- **Pre-demo** (demo is "tomorrow", Sep 10): run `core/reverify_controls.py` ~30 min
  before; commit fresh controls_reverify.json. Tagged GitHub release still pending
  (`~/.local/bin/gh release create`) once surface settles.

## 6. Quick commands

```bash
cd ~/joulectrl-a
git pull --rebase origin main
.venv/bin/python -m pytest tests/unit -q          # 175 green expected
./scripts/launch_dashboard.sh                     # full stack + browser
gio launch ~/.local/share/applications/joulectrl.desktop   # GNOME app
.venv/bin/python -m helper.client read_energy     # helper health
.venv/bin/python -m helper.client restore         # panic button
(cd frontend && npm run build)                    # after frontend edits
kill $(cat /tmp/joulectrl-api.pid)                # stop API
```

## 7. Commit conventions (keep them)

- Author: `agent-a <agent-a@joulectrl.local>`, committer:
  `GIT_COMMITTER_NAME="dan-el-7" GIT_COMMITTER_EMAIL="dan-el-7@users.noreply.github.com"`,
  and ALWAYS append trailer `Co-authored-by: dan-el-7 <dan-el-7@users.noreply.github.com>`
  (owner explicitly wants joint credit on every commit).
- Prefix `[a]`, push after every unit, pull --rebase first. AGENTS.md §8 log line per
  meaningful unit. Measurement windows: `[measuring]`/`[done-measuring]` pushed immediately.
