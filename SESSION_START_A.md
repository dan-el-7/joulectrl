# SESSION_START_A.md — READ AGENT_A_HANDOFF.md FIRST (Sep 9 2026 ~17:25Z)

The complete, current handoff for any successor (incl. Antigravity) is now
AGENT_A_HANDOFF.md in this repo root. It supersedes the brief below, which is
kept for A#1→A#2 history.


You are Agent A (Hardware & Measurement) on the joulectrl 4-agent team. This file is the
complete context you need. Written 2026-09-09 ~12:30 UTC by session A#1 when it ran low on
tokens. Your predecessor completed ALL Agent A gate items — you are on standby/support +
polish, not behind.

## Identity & setup

- Clone: `~/joulectrl-a` (venv: `.venv`). Remote: https://github.com/dan-el-7/joulectrl (main).
- Git identity: author `agent-a <agent-a@joulectrl.local>` (already configured in the clone).
  When committing, use committer credit for the owner:
  `GIT_COMMITTER_NAME="dan-el-7" GIT_COMMITTER_EMAIL="dan-el-7@users.noreply.github.com" git commit ...`
  (This is the agreed pattern: agent attribution + owner's contribution graph.)
- Every session: `cd ~/joulectrl-a && git pull --rebase origin main`, re-read AGENTS.md §8/§9
  logs + AGENTS2.md + HANDOFF.md, check AFFECTS(a) lines, increment session to A#2 in
  AGENTS2.md, post heartbeat.
- The binding contract is AGENTS.md in the repo root. Your files: core/discovery.py,
  core/topology.py, core/calibration.py, core/run_c1.py, core/run_c2*.py, core/doctor.py,
  core/reverify_controls.py, core/watch_cosign_test.py, energy/, helper/, fixtures/real/,
  .github/workflows/ci.yml. Touch nothing else — AFFECTS(<owner>) notes instead.

## Current machine state (verify at session start)

1. Helper daemon: `python3 -c "from helper.client import HelperClient; print(HelperClient().read_energy())"`
   — if it fails, restart: `pkexec /home/dan-el/joulectrl-a/helper/daemon.py` (passwordless;
   polkit rule /etc/polkit-1/rules.d/49-joulectrl-helper.rules matches ONLY this exact path).
2. Stock state: `cat /sys/devices/system/cpu/cpufreq/boost` (expect 1),
   policy0/scaling_max_freq (5090000), policy1 (3506494). If not stock: `python3 -m helper.client restore`.
3. Sleep inhibitor (dies on reboot, by design): `systemd-inhibit --list | grep joulectrl`.
   If absent: `systemd-inhibit --what=sleep:idle:handle-lid-switch --mode=block --who=joulectrl
   --why="hackathon measurement session" sleep infinity &` (background, nohup-style).
4. AC power must be on for measurements: `cat /sys/class/power_supply/ACAD/online` (expect 1).

## Verified machine facts (do NOT rediscover; full details in fixtures/real/)

- powercap `/sys/class/powercap/intel-rapl:0/energy_uj` package-0 counter: root-only,
  65,532,610,987 uJ wrap range. All energy reads go through the helper.
- Core classes: even CPUs = Zen 5 (fast, 5.09 GHz max), odd = Zen 5c (efficient, 3.51 GHz).
- 16 per-CPU cpufreq policies. Caps bind ONLY with boost=0 — and sub-base caps (<2 GHz) are
  accepted-but-IGNORED (cur_freq stays ~1.99 GHz under load; verified under both governors).
  Effective control space = 2 points/class: stock (boost=1) and base (boost=0).
- boost=0 clamps cpuinfo_max_freq to 2000000 kHz on BOTH classes.
- amd-pstate readback is ASYNC — retry reads after writes (helper does this internally).
- Helper watchdog kills the lease after 30 s without heartbeat — any long measurement loop
  MUST call c.heartbeat() around runs (bit A#1 once).
- tuned (throughput-performance) + tuned-ppd + nvidia-powerd run; they did not fight caps
  in tests. Don't stop them without human approval.

## Key data (all committed, boot_id-fingerprinted)

- `fixtures/real/calibration_c2_effective.json` — CANONICAL calibration (8 points x 3 reps).
  Demo headline: fast/base/w4 = 10.78 s / 60.4 J vs fast/stock/w4 = 4.24 s / 85.8 J
  → **-30% package energy at 2.55x runtime**.
- `fixtures/real/calibration_c1.json` (single-core baselines), `calibration_c2.json`
  (16-row sweep + gate_b_findings), `capability_report.json`, `topology.json`,
  `controls_reverify.json` (Gate 4 PASS).
- Watch detector co-sign: PASSED on real hardware (B's core/watch.py within 1 poll interval
  of true runtime; core/watch_cosign_test.py reruns it).

## What's left for A (standby + polish)

1. **B wires `joulectrl doctor`** (AFFECTS(b) logged; library ready: core/doctor.py
   doctor_report()/format_doctor()). Answer questions if B asks.
2. **Live validation runs**: when B/C run real workload validation for the demo, bracket
   with [measuring]/[done-measuring] lines in AGENTS2.md + push immediately (B defers heavy
   loops during windows). Machine must be quiet (no LLM, no browser bloat on this laptop).
3. **Pre-demo re-verify**: `core/reverify_controls.py` (~30 s) — run it again close to demo
   time; commit fresh controls_reverify.json.
4. **Polish**: tagged release (git tag + GitHub release via `~/.local/bin/gh release create`)
   once the team's API/CLI surface settles; README already documents usage.
5. Watch the board: pull often, answer AFFECTS(a), keep heartbeat <15 min while active.

## Rules that bit A#1 (do not repeat)

- Quote heredocs containing backticks — bash eats them (mangled AGENTS2.md once).
- `pkexec` for anything except daemon.py prompts (and can HANG in a background shell) —
  never call it on other programs; route root work through the helper.
- pkill patterns matching your own shell's command line kill your own terminal call.
- Long measurement loops need helper heartbeats (watchdog = 30 s).
- C2-style sweeps: restore to TRUE stock between classes (apply leaves boost=0 behind).
- Measure energy bracketing the run: read_energy BEFORE launch and AFTER termination.

## Team snapshot at handoff (verify with git pull — this may be stale)

- B: models v0, store, runner, CLI (layouts/check-calibration/run-fixed), optimizer tested
  on real C2 data, watch detector + suggest_budget. Doctor wiring pending (flagged).
- C: FastAPI + React dashboard (Setup/Explorer/Validation/Watch views), SSE on B's EventBus,
  watch endpoints, validation-points route. API on 127.0.0.1:8000, docs/API.md is the contract.
- D: compute kernel (checksums verified), workload plugins + presets (calibration/c2_sweep
  presets match A's real runs), explain layer, demo/run_demo.py citing real calibration data,
  integration tests (39 green).
- CI green on main; 169 unit tests green in this clone.
