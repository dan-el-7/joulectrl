# SESSION_START_D.md — new Agent D session brief (read this FIRST)

You are Agent D (Workloads, Explanations, Verification, Tests & Demo) on the joulectrl 4-agent team.
This file contains the complete context needed for any fresh or successor session.
Your predecessor completed ALL Gate 1–4 deliverables — 100% green test suite, all contracts satisfied.

## Identity & Setup

- Working directory: `joulectrl` clone on `main` branch.
- Remote: `https://github.com/dan-el-7/joulectrl` (main).
- Git identity: `agent-d <agent-d@joulectrl.local>`.
- Binding contract: `AGENTS.md` (process & ownership boundaries).
- Live state & handoff: `AGENTS2.md` and `HANDOFF.md`.
- Session protocol:
  1. `git pull --rebase origin main` before any work.
  2. Inspect `git log -n 5`, `AGENTS.md` status logs, and `AGENTS2.md` live state.
  3. Keep heartbeat in `AGENTS2.md` fresh (< 15 min).

## Agent D Ownership Map

You own and edit ONLY:
- `workloads/` (`base.py`, `clean_build.py`, `fixed_compute.py`, `registry.py`, kernel in `workloads/kernel/`)
- `explain/` (`facts.py`, `templates.py`, `providers.py`)
- `tests/integration/` (`test_workload_lifecycle.py`, `test_runner_workload.py`, `test_validation_export.py`, `test_watch_mode.py`)
- `tests/unit/` (`test_compute_kernel.py`, `test_workloads_base.py`, `test_clean_build.py`, `test_contrast_workload.py`, `test_explain.py`)
- `demo/` (`run_demo.py`, `README.md`)
- `fixtures/synthetic/` (`synthetic_profile.json`, `synthetic_selection.json`, `synthetic_validation_pairs.json`, `synthetic_calibration.json`)
- `SESSION_START_D.md`

Never edit files owned by A, B, or C (`core/models.py`, `core/store.py`, `core/runner.py`, `core/watch.py`, `helper/`, `api/`, `frontend/`).
Log cross-cutting observations with `AFFECTS(<owner>)` in `AGENTS.md`.

## Test Suite Execution (39 Tests Green)

Run the full Agent D test suite with standard library `unittest`:
```bash
python -m unittest tests/unit/test_compute_kernel.py tests/unit/test_workloads_base.py tests/unit/test_clean_build.py tests/unit/test_contrast_workload.py tests/unit/test_explain.py tests/integration/test_workload_lifecycle.py tests/integration/test_runner_workload.py tests/integration/test_validation_export.py tests/integration/test_watch_mode.py
```

## Deterministic Compute Kernel & Checksums

The compute kernel (`workloads/kernel/fixed_compute.c`) executes fixed work with strict checksum invariance across worker thread counts:
- `smoke` (`-c 1024 -i 50000`): `0x23e23165be5ef4b6`
- `light` (`-c 2048 -i 50000`): `0x8d10852193c21759`
- `standard` (`-c 4096 -i 100000`): `0x3a762069507139ac`
- `heavy` (`-c 8192 -i 100000`): `0x38a6af54e0c98b86`
- `calibration` C1 (`-c 16384 -i 200000`): `0xc2493c07d6b29c85` (matches Agent A real C1 single-core)
- `c2_sweep` C2 (`-c 32768 -i 200000`): `0x4f59b8763583e750` (matches Agent A real C2 dense sweep across all 16 rows)

## Live Demo Presentation (`demo/run_demo.py`)

Run the complete 5-phase live demonstration script:
```bash
python demo/run_demo.py
```
Or run specific phases:
```bash
python demo/run_demo.py --phase capabilities
python demo/run_demo.py --phase kernel --preset light
python demo/run_demo.py --phase watch
python demo/run_demo.py --phase pareto
python demo/run_demo.py --phase optimizer
python demo/run_demo.py --phase validation
```

## Verified Real Hardware Facts (Fedora Demo Laptop)

- **Machine**: AMD Ryzen AI 7 350 w/ Radeon 860M (8 physical cores, 16 logical threads).
- **Core Classes**: Zen 5 (even CPUs 0,2,4,6 up to 5.09 GHz) and Zen 5c (odd CPUs 1,3,5,7 up to 3.51 GHz). Empirically confirmed 1.45x single-core throughput ratio in C1.
- **Control Space**: Sub-base caps (< 2.0 GHz) are ignored by hardware/driver under `boost=0`. Effective control space is 2 points per class:
  - Stock (`boost=1`): Fast Zen 5 (4w) = 4.24s / 85.8 J.
  - Base (`boost=0`): Fast Zen 5 (4w) = 10.78s / 60.4 J.
  - **Tradeoff Headline**: Base saves **29.6% package energy** at 2.55x runtime.
- **Pre-Demo Controls Re-verification**: Passed and verified restored in `fixtures/real/controls_reverify.json`.

## Gotchas & Lessons Learned

- **Windows Console Encoding**: Never use unicode math symbols in explanation templates or console output. Always use ASCII `<=`, `>=`, `->` to avoid `UnicodeEncodeError` on Windows cp1252 consoles.
- **SQLite Resources**: Always explicitly close SQLite `Store` connections in integration test teardown to prevent `ResourceWarning: unclosed database` noise.
- **Synthetic Energy Backend**: `advance_uj` must advance monotonic time (`_simulated_time_s`) even during simulated counter outage periods.
- **Grounding Rules (PLAN §10)**: Explanations must strictly reflect measured numbers from `Selection` and `Profile`; never hallucinate unmeasured wattages or exact guarantees.
