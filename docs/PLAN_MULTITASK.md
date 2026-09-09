# Plan: Multi-Task Scheduling, Task Affinity, Catch-Up, and Thermal Guards

> Status: **PLAN ONLY — no implementation.** Written Sep 10 2026 in response to new feedback.
> Extends `docs/PLAN.md` (product truth) and `AGENTS.md` (process). Where this document and
> PLAN disagree, PLAN wins; this doc proposes amendments, it does not override.

## 0. The feedback, restated as requirements

1. **Multiple tasks**: the tool must handle more than one managed task being active at once,
   plus the user doing their own interactive work on the same machine.
2. **Task affinity / landing**: a managed task must still hit its runtime target *even when
   the user runs other things* — the machine's core budget is partitioned so the managed task
   is protected from interference, not just pinned and hoped-for.
3. **Catch-up**: if a task falls behind its schedule mid-run, the tool detects the lag and
   recovers budget (escalate performance, shed competition) — not just fail at the end.
4. **Thermal throttling warnings**: surface when the CPU is thermally throttling, because it
   silently invalidates both performance (deadline risk) and measurement honesty.
5. **Priority task selection**: the user picks which task gets maximum performance when
   demands conflict.
6. **Edge cases**: enumerated and handled honestly (§8).

## 1. What we already have (verified, this machine + repo)

Grounded in `fixtures/real/`, `docs/VERIFIED_DEMO_LAPTOP.md`, and the code as of `c2cf3a3`:

| Fact | Consequence for this plan |
|---|---|
| 8 physical cores: Zen 5 (even CPUs, 5.09 GHz) + Zen 5c (odd, 3.51 GHz) | A **natural partition**: fast class = priority lane, efficient class = background lane. Verified by C1. |
| Effective control space is **2 points/class** (stock boost=1, base boost=0); sub-base caps silently ignored; boost is a **global** knob | Frequency escalation is coarse and *machine-wide*: turning boost on for the priority task also un-caps background tasks. Levers must include **core allocation and worker count**, not just frequency. |
| all8/base saves 52% energy at 1.92x runtime; all16 dominated by all8 (SMT no benefit, this kernel) | More workers ≠ more speed. Oversubscription is measurable and worth avoiding. |
| Package energy counter is **system-wide** (RAPL package-0, root-only via helper) | Concurrent tasks **cannot** get honest per-task measured energy. This is the hardest constraint — see §4. |
| Helper op set frozen: `begin_session, read_energy, apply_configuration, heartbeat, restore, end_session`; one exclusive lease; 30 s watchdog | A scheduler layer must **own** the lease; tasks never hold it individually. New reservation op = contract change (§6). |
| Runner applies affinity via unprivileged `taskset` around the workload command | `taskset` pins the workload but does **not** keep the OS from scheduling other work on those cores. True reservation needs cpuset cgroups (§3.2). |
| `WatchDetector` learns idle baseline and detects activity windows from package power at 0.5–1 Hz | Reusable as an **unmanaged-load detector** and progress-rate probe. |
| `RunRecord.warnings: list[str]` already exists; watch-mode records already excluded from selection evidence | Thermal warnings and concurrency attribution flags have a ready-made, honest home. |
| Thermal sensors: `k10temp` (Tctl/Composite), `acpitz` readable; **no AMD throttle-flag sysfs** | Throttling must be **inferred** (temp thresholds + cur_freq-vs-cap under load + power-ceiling anomalies). Never claim a kernel-reported throttle flag we don't have. |

## 2. Concept: from "one experiment" to a deterministic micro-scheduler

The current model is: one exclusive lease, one workload at a time, quiet machine assumed.
The new model is: **one scheduler, many tasks, one noisy machine** — deterministic, no ML,
same philosophy as the optimizer.

```text
                    ┌──────────────────────────────────────────┐
                    │  Scheduler (owns the helper lease)       │
                    │  - admission control (deadline feasible?)│
                    │  - fixed-priority bands + EDF within band│
                    │  - core partition + control level        │
                    │  - catch-up controller (§5)              │
                    │  - thermal guard (§7)                    │
                    └───────────────┬──────────────────────────┘
                                    │ allocations (affinity, workers, boost, caps)
        ┌───────────────────────────┼───────────────────────────────┐
        ▼                           ▼                               ▼
  PRIORITY task              BACKGROUND tasks                UNMANAGED work
  (user-picked)              (queued/parked, lower           (user's browser, LLM,
  fast cores, boost headroom  claim; efficient cores;         compile loops — detected,
  for catch-up                caps/base for energy)          never controlled)
```

Design rules (all inherited from the existing non-negotiables):

- **Deterministic**: allocations come from measured calibration data + explicit policy. The
  LLM explains, never schedules.
- **Measured points only**: the scheduler picks allocations from the calibration curve's
  measured (runtime, energy) points per class/layout; it never extrapolates a frequency that
  Gate B showed to be a silent no-op.
- **Honest degradation**: when the machine is too busy for honest per-task measurement, say
  so in the record; degrade the claim, never fabricate the number.

## 3. Task affinity — making the priority task land

### 3.1 Two levels of protection

**Level 1 — workload pinning (unprivileged, exists today).** The runner already wraps the
command with `taskset`. Extend `Configuration.cpu_affinity` selection from *layout presets*
to *scheduler-computed masks*. Nothing new technically; the change is who computes the mask.

**Level 2 — core reservation (privileged, new helper op).** `taskset` pins our task but the
kernel will happily schedule Firefox on the same cores. To actually protect the priority
task, the helper (root) creates a **cpuset cgroup partition** for the duration:

```text
joulectrl:priority    = 2–4 Zen 5 physical cores (+1 SMT sibling each)
joulectrl:background  = remaining physical cores (Zen 5c or leftover Zen 5)
default (everything else) = background set   ← user's interactive work lands here
```

- Implemented as cgroup v2 `cpuset` writes by the helper; snapshotted and restored exactly
  like frequency settings (same recovery-snapshot → apply → readback → restore lifecycle,
  boot-id fingerprinted). Moving the *root group's* `cgroup.procs` is the part that needs
  root; `sched_setaffinity` of our own processes is not enough because new processes spawn
  into the default group.
- **Fallback ladder when cgroups are unavailable/refused**: Level-1 pinning only, plus
  `nice`/`SCHED_BATCH` on background tasks (unprivileged), plus honest labeling: the run
  record carries `protection: "cpuset" | "affinity-only"`, and deadline predictions widen
  their guard margin accordingly (affinity-only = interference observed in calibration, if
  any). Never claim isolation that wasn't verified — same rule as Gate B readbacks.

### 3.2 The partition is measured, not guessed

The default partition (priority = fast class, background = efficient class) is a *suggestion
from calibration data*: C1 says Zen 5 is 1.45x Zen 5c throughput. But the actual allocation
must come from the same measured curve that drives everything else:

- If the priority task's deadline is loose, the scheduler may give it Zen 5c cores at base
  (lowest energy meeting the deadline — exactly today's selector, applied per-task).
- If tight, priority gets all Zen 5 physical cores at stock, background is parked entirely
  (see §3.4), because **boost is global**: you cannot run priority-at-stock and
  background-at-base simultaneously. The only simultaneously-different lever is *which cores*,
  not which frequency. This asymmetry is a machine fact and belongs in the capability report.

### 3.3 Interactive-work carve-out (the "even if the user does other tasks" case)

Reserve **one physical core pair for the default/unmanaged group by default**. The user's
foreground work (terminal, browser, the dashboard itself) gets a lane that managed tasks
never touch, so the GUI never goes sluggish and the user never has an incentive to kill the
scheduler. Sizing is configurable; the default is conservative (this machine: 1 Zen 5c
physical core + SMT sibling, unless the priority task's guarded runtime doesn't fit without
it — then the UI says so *before* the run, not after).

### 3.4 Preemption semantics

Managed tasks are long-running; "priority" must be defined by what we can actually do
mid-task:

| Workload kind | Preemption available |
|---|---|
| Chunked/checkpointable (our compute kernel; any workload exposing `progress`) | **Pause/resume**: SIGSTOP the process group, re-allocate, SIGCONT. Progress is preserved; energy attribution continues cleanly (task window excludes paused time — see §4). |
| Restartable (clean builds) | **Cancel + requeue from scratch**; scheduler decides if the restart cost beats letting it finish. |
| Black-box (watch-mode tasks, user's own loops) | **None** — only admission control at start. Never SIGSTOP a task we don't own. |

## 4. Energy accounting under concurrency — the honesty problem

This is the requirement that collides with a non-negotiable ("measure, don't estimate";
package energy is a *system-wide* counter). Resolution: three explicit tiers, chosen
automatically and stamped on every record:

| Tier | Condition | Energy claim |
|---|---|---|
| **Exclusive** (today's behavior) | One managed task, quiet mode, watch/power trace confirms no unmanaged load | Per-task measured package energy. Only tier eligible for Pareto/selection evidence. |
| **Partitioned** | Multiple managed tasks, cpuset isolation, no unmanaged load detected | **Session-level** measured energy (exact, whole window) + **estimated per-task split** (core-class utilization × class power from calibration, labeled `attribution: "estimated"`). Estimates never enter selection; they're for the user's intuition. |
| **Contended** | Unmanaged load detected (watch-detector activity outside our partitions) or cgroups unavailable | Energy labeled `contaminated`; comparisons degraded to runtime-only, like timing-only mode. |

Mechanism: the same 0.5–1 Hz package-power polling the watch detector already does becomes a
permanent, featherweight **session monitor** while any task runs. It (a) detects unmanaged
activity (power above the sum of what our partitions should draw — calibrated thresholds),
(b) feeds the catch-up controller (§5), (c) detects thermal events (§7). One poller, three
consumers, zero extra perturbation.

## 5. Catch-up controller (single-task lag recovery)

Goal: a task that falls behind its schedule gets budget back *mid-run*, instead of missing
the deadline at the end.

### 5.1 Progress instrumentation

- **Protocol**: workload plugin contract gains an optional `progress(run_context) ->
  float∈[0,1]`. Chunked kernel: exact (chunks done / total). Builds: approximate
  (ninja log lines, or compile units done). Black-box: absent.
- **Fallback without progress**: rate estimation from the calibrated throughput of the
  current (class, control, workers) point — explicitly labeled `progress: "estimated-rate"`.
- **Watch-detector floor**: if even that is impossible, catch-up is disabled for the task and
  the UI says so at admission time.

### 5.2 The control loop (deterministic)

Every poll interval (1–2 s):

```text
expected = elapsed_time × (work_rate measured this run, smoothed)
lag      = expected_progress − observed_progress
eta      = remaining_work / current_rate
if eta > deadline_remaining × (1 − safety):        # falling behind
    escalate one step down the lever ladder (below)
elif lag recovered and energy objective prefers it:
    de-escalate (return toward the selected energy-optimal point)
```

**Lever ladder, cheapest-honesty first** (each step is re-validated against the measured
calibration point for the new allocation; each escalation is logged in the run record):

1. **Shed competition**: park/stop background managed tasks (their cost: their own deadlines
   slip — scheduler checks they can still land; else it picks whom to fail *explicitly* and
   tells the user).
2. **Expand allocation**: move the task to more/faster cores (Zen 5c → Zen 5; add workers up
   to the class's physical-core count — never past it: all16 is measured-dominated by all8).
3. **Frequency escalation**: base → stock (global boost — which is exactly why this is lever
   3, not lever 1: it also speeds up everything else on the machine).
4. **Admission revision**: if even the max point's guarded runtime misses the deadline,
   transition to the existing `NoFeasibleConfiguration` edge state **and notify** — but do it
   the moment it's detectable, not at the deadline.

**Hysteresis**: escalate at most once per N seconds and require sustained lag (≥3 consecutive
polls), mirroring the watch detector's onset logic — don't oscillate a global boost knob at
1 Hz. De-escalation requires sustained recovery plus a margin.

### 5.3 What catch-up costs

Escalation trades energy for time — the exact tradeoff the tool exists to optimize. The run
record therefore logs the *original selected point*, *every escalation*, and the *final
outcome*, and the comparison card reports against the honest final configuration. "We picked
the 30%-energy-saving point, then the user loaded a model and we spent part of that back to
make the deadline" is a feature demo, not a failure — **if and only if it's disclosed**.

## 6. Contract changes required (frozen-interface protocol)

| Contract | Change | Owner |
|---|---|---|
| `core/models.py` | New: `TaskSpec` (workload, deadline, priority, preemption class), `Allocation` (mask, workers, control point, protection level), `attribution` + `protection` + `progress_mode` fields on `RunRecord` | B (contract protocol, all hands review) |
| Helper op set | New op `set_reservation` (cpuset create/assign/teardown, snapshot+restore semantics identical to frequency settings) — *only* new op; no arbitrary cgroup writes | A |
| Workload plugin | Optional `progress()` in `workloads/base.py` | D |
| API + SSE | `/api/tasks` CRUD + queue state; new SSE events `task.allocation_changed`, `task.escalated`, `thermal.warning` | C |
| Watch detector | Reused as session monitor; thresholds co-signed by A on real hardware (same as §6b co-sign) | B impl, A co-sign |

Ownership split for implementation (when it happens): A — cpuset helper + thermal sensor
reads + unmanaged-load co-sign; B — scheduler, catch-up controller, attribution tiers;
C — queue/priority UI + thermal banner + escalation timeline; D — progress protocol on
workloads + explain templates for escalations + integration tests.

## 7. Thermal throttling detection and warnings

### 7.1 Detection (inferred — no kernel throttle flag exists on this machine)

Three independent signals, polled by the session monitor; any two within a window ⇒ flag:

1. **Temperature thresholds**: `k10temp` Tctl/Composite (and `acpitz` as a corroborating
   zone) crossing machine-derived thresholds. Thresholds come from a short calibration-time
   thermal characterization (5 min at the max control point): record the observed
   steady-state temp under sustained load; set `warn` at steady+Δ and `critical` at a
   configurable ceiling. **No hardcoded 95°C** — same rule as every other machine fact.
2. **Frequency-under-load anomaly**: `scaling_cur_freq` on a busy core sustained ≥ N s
   *below* the applied control point's expected band (we already have per-policy readback
   and the Gate B lesson that readback lies — this is the same check turned into a monitor).
3. **Power-ceiling anomaly**: package power flattens below its calibration-expected envelope
   while work rate also drops — the throttling signature as seen from our own counter.

Single-signal hits are logged as `warnings` on the RunRecord; two-signal confirmation raises
a UI **banner** ("CPU is thermally throttling — measurements may be unreliable, deadline
risk elevated").

### 7.2 Consequences (what a warning *does*)

- **Measurement honesty**: confirmed throttling marks affected runs `thermally_contaminated`
  → excluded from selection evidence (like watch mode); profile-validity trigger (PLAN §12
  already lists environment changes; thermal state joins that list).
- **Catch-up interaction** (the subtle one): lever 3 (boost) *increases* heat. The catch-up
  controller must treat thermal state as a budget: if `critical` is active, escalation is
  **blocked** (or reversed) and the scheduler reports "cannot catch up without overheating;
  deadline X will be missed by ~Y s" — the honest answer, not a forced boost into a
  throttle spiral that lands *later* anyway.
- **Calibration guard**: throttling during a calibration sweep invalidates affected points;
  sweep must either re-run them or mark them (sweep_check already does margin checking —
  extend, don't replace).

## 8. Edge cases (explicit, honest states — never force green)

**Scheduling / admission**
- Two tasks whose deadlines conflict even with exclusive resources → admission control
  rejects or queues the second *up front*; never silently run both into the ground.
- Priority changed mid-run → cheap re-plan (recompute allocations), not a restart;
  escalation timeline shows the re-plan.
- Priority task finishes → background tasks un-park automatically; partition re-widens;
  de-escalate to their energy-optimal points.
- Total worker demand exceeds physical cores → never oversubscribe past the measured
  all8/all16 result; queue instead.
- Task with no deadline (energy-only objective) → lowest claim tier; always first to be
  parked.

**Interference**
- User launches a heavy unmanaged task mid-run → session monitor detects, attribution drops
  to Contended tier, catch-up engages for deadline-holding tasks, record discloses the
  window. We do **not** kill or nice the user's processes — read-only respect.
- The dashboard/API itself competing → dashboard stays in the unmanaged carve-out (§3.3);
  SSE rates throttle during measurement windows (quiet mode, unchanged).
- Another joulectrl experiment (second lease attempt) → unchanged: one lease, the scheduler
  holds it; CLI/daemon both go through it.

**Catch-up failure modes**
- Escalation ladder exhausted → `NoFeasibleConfiguration` + notification at detection time,
  not at deadline; run continues or user cancels (their call, in the UI).
- Progress signal lies (workload reports 100% but verify() fails) → verify remains the truth;
  catch-up pauses on inconsistent progress; run marked unstable, not retried to flattery
  (existing rule).
- Oscillation suppression fails (boost flapping) → hysteresis + minimum dwell; if it still
  oscillates, latch at the higher point and disclose the energy cost.

**Thermal / power / environment**
- Throttle during a *calibration* sweep → §7.2; re-run or mark affected points.
- AC→battery mid-run → existing environment-change trigger extended: scheduler parks
  background tasks, priority task escalates or finishes honestly; energy claims get a
  battery-mode caveat.
- Thermal sensor absent (other machines) → thermal guard degrades to signals 2+3 only;
  capability report states it (doctor gains a `Thermal monitoring` line).

**Restoration safety (extends the existing non-negotiable)**
- cpuset partitions are a *touched setting*: same snapshot → apply → readback → restore
  lifecycle as frequencies; restore must move processes back and delete the cgroups;
  heartbeat loss triggers restore of **everything**, partitions included.
- Crash mid-reallocation (partition changed, task not yet moved) → recovery snapshot replay
  is idempotent; stale-snapshot rules (boot id) unchanged.
- The unmanaged carve-out must be restored too — leaving the user's desktop permanently
  restricted to one core would be a self-inflicted wound.

## 9. What we will NOT do (scope guard, deliberately)

- No per-process energy attribution claims beyond labeled estimates (counter is package-wide).
- No real-time scheduler tricks (`SCHED_FIFO`), no autogroup fights, no nice-ing processes we
  don't own.
- No permanent background tuning (unchanged out-of-scope): partitions exist only inside a
  scheduler session and are always restored.
- No frequency interpolation between the 2 measured control points on this machine — the
  ladder moves between *measured* points or not at all.
- No ML scheduler. Deterministic policy + measured data, same as the optimizer.

## 10. Build order (when implementation is green-lit)

```text
M0  Instrumentation:  session monitor (poller), thermal sensors, progress protocol,
                      TaskSpec/Allocation models (contract change)          [B,A,D]
M1  Soft scheduling:  queue + priority + admission + affinity-only masks,
                      no cgroups, Exclusive/Contended tiers only           [B,C]
M2  Catch-up:         progress loop + lever ladder + escalation records    [B]
M3  Hard partition:   helper set_reservation, cpuset isolation, Partitioned
                      tier, restore-lifecycle extension                    [A]
M4  Thermal:          characterization at calibration time, 3-signal detector,
                      guard on escalation, UI banner                       [A,C]
M5  Polish:           escalation timeline UI, explain templates, integration
                      tests, doctor line, docs                             [C,D]
```

M1–M2 deliver the visible feature (priority task that lands + catch-up) without touching the
frozen helper contract; M3/M4 are the privileged/hardware layers behind flags. Each
milestone leaves `main` installable and tests green, per the working contract.

---

### One-paragraph summary for the team

Multiple tasks turn the single experiment lease into a deterministic micro-scheduler that
owns the lease, partitions cores (fast class = priority lane, efficient class = background,
plus a protected lane for the user's own work), and picks each task's allocation from the
already-measured calibration curve. Because boost is global on this machine, the real
mid-run levers are core allocation and worker count, with frequency escalation last.
Per-task energy under concurrency is honestly labeled (measured session total, estimated
split) and never enters selection evidence. A progress-driven catch-up controller escalates
ladders deterministically with hysteresis, blocked by a thermal guard that infers throttling
from k10temp + frequency-under-load + power-envelope signals (no kernel flag exists here).
Everything a scheduler touches — frequencies, cgroup partitions, even the user carve-out —
goes through the existing snapshot/readback/restore lifecycle.
