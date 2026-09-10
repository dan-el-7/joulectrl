# Review-Fix Handoff (GLM 5.3 audit of bc63e2a + a602836)

Working directly in `/home/dan-el/joulectrl-a` (main branch). Baseline before
changes: `244 passed, 1 skipped` (the zstd-test failure on fresh clones is now
a hermetic skip). Final state: **251 passed, 2 skipped, 0 failed**. Demo-safe:
no API contract, frontend, or workload behavior changes; helper client
protocol unchanged; running helper daemon must be RESTARTED (pkexec relaunch)
to pick up the new auth code. Reference clone of bc63e2a at
`/tmp/joulectrl-review` (stale, do not edit).

## Step 1 ✅ helper/daemon.py — real SO_PEERCRED auth (CRITICAL)
- `handle_conn` resolves `SO_PEERCRED` (getsockopt + struct.unpack) and REFUSES
  the connection before reading a byte unless the kernel-verified uid is in
  `ALLOWED_UIDS = {0, PKEXEC_UID or 1000}`. Previously: socket 0666, uid/pid
  taken from client-supplied JSON (spoofable), no peercred at all.
- `op_*` take an optional `peer` dict; `begin_session` uses the kernel peer
  (client uid/pid args ignored). `peer=None` fallback keeps direct unit-test
  invocation working.
- Socket perms 0660 + chown to first allowed non-root uid (so the real client
  still connects); untrusted users blocked by perms AND gate.
- Fixed latent NameError: `op` unbound after `json.JSONDecodeError` → `op=None`.
- Removed unused `subprocess` import; added `struct`.
- Tests +2 in test_helper_daemon.py (peer spoof ignored; untrusted uid refused).

## Step 2 ✅ api/engine.py `_run_one` — wrap-safe + plausibility ceiling
- The helper-bracket override (~line 849) is the ONLY energy source in this
  path (runner built with `WorkloadRunner(None)`), so kept, not removed.
  Added the `EnergyAccumulator`-style guard: `(e2-e1) % WRAP_UJ` now also
  checked against a 200W ceiling over (runtime + 1s settle). Implausible delta
  (reset/multi-wrap) → `energy_available=False` + `metadata["energy_error"]`
  instead of a bogus Joules number.

## Step 3 ✅ core/watch.py — adaptive baseline + segment reset guard
- `WatchDetector._adapt_baseline()`: rolling re-estimation of median/spread
  from in-band samples while idle with NO pending spike candidate (window
  capped at baseline_window_s/poll_interval_s). Baseline frozen during
  candidates/active segments so workload ramp-up can't be absorbed into the
  threshold. Fixes permanent baseline staleness after ambient drift.
- `WatchSegment.energy_j`: delta checked against `PLAUSIBLE_MAX_W=200W` over
  segment runtime — counter reset mid-segment returns None (unavailable).
- Tests +2 in test_watch.py (gradual drift still detects spikes; implausible
  segment delta → None).

## Step 4 ✅ core/validation.py — thermal cooldown between pairs
- `ValidationRunner._thermal_cooldown()` runs before each pair: waits until
  k10temp/zenpower/coretemp reads ≤ `cooldown_temp_c` (default 50°C), bounded
  by `cooldown_max_wait_s` (default 20s), then proceeds anyway. No sensor
  readable → skip immediately (never blocks CI). New ctor kwargs, defaults
  preserve old behavior for existing callers.
- Tests +3 in test_validation.py (cools → no flag; timeout → metadata flag;
  no sensor → instant skip).

## Step 5 ✅ hermetic zstd test + dead code + daemon partial-apply
- test_custom_command.py: zstd test now skips with an explanatory message when
  `workloads/build_target/zstd` is absent (fresh clones); added a fallback
  test asserting mode="zstd" degrades to the documented single-file gcc
  compile when the tree is missing (skips when tree present).
- energy/base.py: removed dead `EnergyReading` walrus-hack class (no refs).
- helper/daemon.py `op_apply_configuration`: validates ALL policy names/caps/
  governors BEFORE writing anything — no more partial application on error
  (snapshot/restore still covers any residual risk).

## Final state
- 251 passed, 2 skipped (pre-existing skip + conditional fallback skip), 0 failed.
- Files touched: api/engine.py, core/validation.py, core/watch.py,
  energy/base.py, helper/daemon.py, 4 test files, this handoff.
- Push: committed on main, pushed to origin (github.com/dan-el-7/joulectrl).
