# Final Event Plan: `joulectrl`

> **Find the lowest energy needed to get the job done on time.**

Build a local-first Linux tool that profiles a repeatable workload, measures CPU-package energy and runtime, selects the lowest-energy measured configuration within a runtime budget, and verifies that selection with fresh executions.

The optimizer is entirely deterministic. An LLM is an optional explanation interface—not a dependency, measurement source, or CPU controller.

**For the event: support the Fedora demo laptop well, architect for other Linux hardware, and do not promise universal hardware support.**

---

## 1. Decisions to Lock Before Building

| Area | Final decision |
|---|---|
| Working name | `joulectrl` (conflict checked: free on PyPI and GitHub, Sep 2026) |
| Primary objective | Minimum measured CPU-package energy within a runtime budget |
| Secondary mode | Explore the energy/runtime Pareto frontier |
| Event platform | Fedora on the demo laptop |
| Primary workload | Repeatable clean compilation |
| Contrasting workload | Small compiled fixed-work CPU benchmark |
| Optimization | User-selected points from the measured calibration curve, with optional workload validation; no fixed configuration grid |
| Controls | Supported frequency caps plus topology-aware CPU affinity and worker count |
| Fallback control | Supported energy-performance preferences if frequency caps are ineffective |
| Calibration | Dense per-class performance-per-watt sweep (all/most frequency points reachable, or the best available fallback tier) via the standardized compute kernel, with a user-selected calibration-time budget once per machine; the full measured curve is retained for visualization and validation |
| Measurement | A verified hardware-reported package-energy counter |
| Validation | Fresh baseline and selected-configuration runs |
| Explanation | Deterministic templates always; optional local or cloud LLM |
| Application | Apply for the experiment/run, then restore |
| Business direction | Free local utility → paid policies and reporting for recurring dedicated compute |

### Explicitly Out of Scope

- GPU or NPU optimization.
- Undervolting, overclocking, custom kernel modules, or raw-MSR tuning.
- CPU hotplugging.
- Permanent autonomous background tuning.
- Process-level energy attribution.
- Windows/macOS support.
- Arbitrary shell commands entered through the dashboard.
- Fleet management, accounts, telemetry sales, or model training.

These cuts make the project plausible in 36 hours.

---

## 2. Hardware-Specific Implementation

This plan assumes the machine has an **AMD Ryzen AI 7 350**, rather than another similarly named Ryzen model.

The exact Fedora/kernel/firmware combination has not been verified here. **Energy-counter access and effective controls remain verification gates, not assumed capabilities.**

### CPU: Do Not Treat It as Eight Identical Cores

The Ryzen AI 7 350 is an **8-core/16-thread processor with a mix of Zen 5 and Zen 5c cores**.

Topology discovery must record:

- Logical CPU IDs.
- Physical-core and package relationships.
- SMT sibling groups.
- cpufreq policy domains.
- Core-class or performance-ranking information, where reliably exposed.

Do not assume:

```text
CPU IDs 0–3 = the four faster physical cores
```

Do not infer core type solely from CPU numbering.

For the MVP, permit a **verified machine-specific topology preset**. If Linux does not expose reliable class information, display the exact CPU mask rather than inventing “performance-core” labels.

### GPU: Useful for Explanations, Irrelevant to Optimization

An 8 GB RTX 5050 is a plausible device for a **7–8B instruct model at approximately 4-bit quantization**, but fitting depends on:

- Model architecture and quantization format.
- Context length.
- KV-cache allocation.
- Inference backend.
- Display VRAM usage.
- Other applications.
- Driver and backend compatibility.

Expect roughly **4–6 GB for quantized weights**, plus runtime and KV-cache memory. An 8 GB card can therefore be workable with a modest context, but it is not a universal guarantee.

**Do not spend event hours fighting GPU inference before CPU measurement works.**

The NPU is not needed for this project.

---

## 3. First Milestone: Hardware Feasibility Gate

Before building the dashboard, implement:

```bash
joulectrl doctor
```

It should produce a capability report, not just hardware names.

### Example Report Structure

```text
CPU topology:              discovered
SMT relationships:         discovered
Core-class mapping:        verified / unavailable
Scaling driver:            detected driver
Frequency-cap control:     verified / ineffective / unavailable
EPP control:               verified / unavailable
Package-energy source:     detected source / unavailable
Energy-counter access:     available / permission required
Power-management conflict: detected / none detected
NVIDIA inference:          optional, not yet tested
Recommended mode:          full / reduced-control / timing-only
```

These are fields to implement—not claims about what the machine will expose.

### Read-Only Discovery Commands

```bash
uname -r
lscpu
lscpu -e=CPU,CORE,SOCKET,ONLINE

cat /sys/devices/system/cpu/amd_pstate/status 2>/dev/null

grep -H . /sys/devices/system/cpu/cpufreq/policy*/{scaling_driver,scaling_governor,scaling_min_freq,scaling_max_freq,cpuinfo_min_freq,cpuinfo_max_freq,energy_performance_available_preferences} 2>/dev/null

find -L /sys/class/powercap -name energy_uj -print 2>/dev/null

perf list 2>/dev/null | grep -Ei 'energy|rapl'

grep -H . /sys/class/hwmon/hwmon*/name \
  /sys/class/hwmon/hwmon*/energy*_label 2>/dev/null

nvidia-smi
```

Discover interfaces; **do not assume an Intel-style powercap path exists on this AMD laptop**.

### Gate A: Can You Measure Package Energy?

Investigate available, documented interfaces:

1. A powercap package-energy counter.
2. A supported system-wide `perf` energy event.
3. A documented hwmon package-energy counter, if exposed.

Implement **one working backend first**, behind an interface that permits others later.

A listed event is insufficient. Verify that it can actually be read, advances during a workload, and reports sensible units.

Record:

```text
backend
counter/domain name
scope
units and scale
rollover behavior
permissions
```

Do not substitute any of these for measured CPU-package energy:

- TDP × runtime.
- CPU utilization × estimated watts.
- Battery discharge.
- NVIDIA GPU power.
- A sum of overlapping package and core counters.

**A core-only counter must not be relabeled as package energy.**

#### If Package Energy Is Unavailable

Time-box investigation. Do not turn the hackathon into AMD driver development.

Options:

- Use another verified Linux machine, if event rules allow.
- Demonstrate timing/control functionality with energy optimization explicitly unavailable.
- Use a clearly labeled replay of real measurements from another identified machine.
- Use an external meter only if the measurement scope is explicitly changed to whole-system energy.

If the laptop has no accessible package-energy source, **the measured-package-energy demo cannot honestly run on it**.

### Gate B: Do Controls Actually Work?

Test two substantially different supported settings on the same fixed workload.

Check:

- Write succeeds.
- Readback matches an accepted setting.
- No competing service immediately overwrites it.
- Actual behavior is consistent with the intended control.

Readback alone does not establish that the CPU operated at the requested frequency. Verify
empirically: pin a busy thread to a CPU under the candidate setting and check
`scaling_cur_freq` actually tracks the cap. (Concrete case, demo laptop: with the global
boost knob on, a 2 GHz cap reads back as accepted while cur_freq stays ~5 GHz — the control
is a silent no-op until boost is turned off. Gate B is what catches this class of problem on
any machine.)

Preferred control order:

1. Frequency caps (paired with boost state as needed) + affinity + worker count.
2. EPP preferences + affinity + worker count.
3. Affinity + worker count only.

If EPP is used, label settings as preferences—not GHz.

Do not change `amd_pstate` mode or kernel boot parameters during normal experiments.

### Gate C: Fedora Environment Stability

Check for:

- TuneD / tuned-ppd / power-profiles-daemon, depending on installation.
- AC versus battery operation.
- Platform power profile.
- Thermal conditions.
- Background updates and indexing.

Do not silently stop system services or disable SELinux/Secure Boot. Any temporary service-policy change must be explicit, recorded, and restored.

### Go/No-Go Requirement

> One correct workload run with valid energy/runtime data, followed by verified restoration.

---

## 4. Event MVP

### Workload A: Repeatable Clean Build

Choose a pinned, offline C/C++ project and fixed build target.

A project such as `zstd` is a reasonable starting candidate. If its build is too short to measure cleanly, select a larger project early.

Aim for roughly **10–25 seconds at baseline**, but do not force the product around an illustrative 20-second deadline.

#### Workload Contract

```text
Fixed source revision
Fixed compiler and flags
Fixed target
Compiler caching disabled
Clean output state before each run
Consistently warm filesystem cache
Worker count explicitly controlled
Successful artifact + functional smoke test
```

For a CMake/Ninja workload:

```text
Prepare, outside measurement:
    configure once
    remove previous build outputs

Measure:
    ninja -C build -j N fixed_target

Verify, outside measurement:
    expected artifact exists
    smoke test passes
```

Label the measured operation accurately: **build-command execution**, not the entire preparation-and-test pipeline.

Do not compare clean builds with incremental builds.

### Workload B: Tiny Compiled CPU Benchmark

Use C/C++ with OpenMP or a small native worker pool—not a Python loop affected by the GIL.

Requirements:

- Fixed total chunk count.
- Fixed work per chunk.
- Chunks partitioned across workers.
- Deterministic checksum.
- Checksum independent of worker count.
- No fixed-duration stopping condition.

A parallel unsigned-integer computation with independent chunks is sufficient. Ensure the compiler cannot eliminate the work.

Changing from four to eight workers must not double the total computation.

This workload uses the **same harness**, not a second profiling system.

Its purpose is to demonstrate workload dependence. If its optimum does not shift, show that honestly.

### Calibration Sweep: Building the Performance-per-Watt Curve

Before picking the grid's control levels (below), build an actual **measured** curve instead
of guessing round percentages. This runs once per machine (not once per workload), using the
**same standardized, fixed-work compute kernel as Workload B** — chunked, deterministic
checksum, checksum independent of worker count — driven at each core-class's natural
full-physical-core layout (Layout A's shape for the faster class, Layout D's shape for the
efficient class: one SMT sibling each, worker count = that class's physical-core count).
Reusing the workload's own harness means no second profiling system to build or trust.

**Sweep-density ladder.** Attempt the top tier first; only drop to the next tier when Gate B–
style verification shows the tier above genuinely does not work on this machine — never
pre-emptively degrade:

1. **Discrete frequency list exposed** (legacy acpi-cpufreq/intel_pstate-style
   `scaling_available_frequencies`) → test **every** listed step. The list is inherently small
   (commonly well under twenty entries), so this is a literal, cheap "test them all."
2. **Continuous cap range, no discrete list** (amd_pstate-style — the demo laptop's case) →
   $N$ evenly spaced cap values from the class's verified min to its verified max, boost held
   at whatever state Gate B found necessary for caps to bind. $N$ is computed from the time
   budget below, not hardcoded.
3. **Caps ineffective** → every supported EPP preference value (typically 2–4). Label the axis
   a preference tier, not GHz — same rule as everywhere else in this plan.
4. **No effective control at all** → skip curve generation for that class; record it plainly in
   the capability report; that class's grid rows fall back to affinity + worker-count only
   (already-specified fallback — nothing new needed there).

**User-selected time budget.** Calibration time is a user-facing parameter, not a fixed product constant.
The user may choose any positive finite duration or **Unlimited / Exhaustive**. The tool estimates
the minimum reliable duration from the measured per-point cost and refuses to pretend that a very
short run is precise. The minimum is a warning threshold, not a hidden hard-coded 10–15 minute
target.

Let $B$ be the requested calibration budget, $K$ the number of discovered classes, and
$t_{point}$ the empirically measured cost of one point (apply + readback + settle + kernel run).
Before the sweep, run a small timing probe and compute:

$$
N_{class} = \left\lfloor \frac{B/K}{t_{point}} \right\rfloor
$$

For finite budgets, the scheduler spends the available time adaptively: first guarantee a
minimum number of well-spaced points per class, then use remaining time for finer frequency
coverage and/or repeated measurements. It must never silently turn a requested long run into a
short coarse run. Progress and the planned/actual point count are visible.

**Minimum reliable duration.** Define a quality floor before starting the sweep, based on the
minimum point count needed to establish the curve shape plus required repeats for the measurement
noise observed during the timing probe. If the requested duration is below that floor, show a
blocking confirmation warning such as: “3 min is below the estimated 11 min minimum for reliable
calibration; results may be noisy or incomplete.” The user can continue unless `--strict` is set.
`--strict` aborts below the floor. The floor is machine-dependent and must be reported with its
inputs, never hard-coded as a universal number.

**Unlimited / exhaustive mode.** `--time unlimited` (also accepted as `--time 0`) removes the
time ceiling. For a discrete frequency list, test every listed frequency and repeat measurements
until the configured convergence criterion is met. For a continuous cap range, “all frequencies”
means every **distinct control point the kernel/driver can actually request and the readback can
distinguish**, using the driver's effective control/readback resolution. Do not claim to test
uncountably many real-valued frequencies. If the effective resolution would make exhaustive mode
prohibitively large, show the estimated work and let the user cancel or switch to a finite budget.

For finite budgets, never use a fixed “10–20 points per class” ceiling. More time means more
coverage and/or repetitions; less time means fewer points with an explicit quality warning.
Exhaustive mode is the only mode that promises complete coverage of the measurable control space.

**Storage.** Same `CalibrationRecord` contract already defined — no schema change, just many
more rows per class. Still tagged so these never mix into workload Pareto/selection evidence
(unchanged non-negotiable).

**Feeding workload validation.** The calibration curve is no longer reduced to a fixed three-level
configuration grid. Layout A and Layout D each retain their **own class's** curve. The complete
measured curve is exposed to the user in the Profile Explorer. The user may select any measured
control point(s) for expensive workload validation; convenience suggestions are derived from the
curve, not a hidden fixed grid.

**Reuse for a workload the user brings later.** The curve is a property of the machine's
silicon/firmware/governor state, not of any one workload — it does not need re-running per
workload, only when that machine-level state changes (same invalidation triggers as Profile
Validity, §12). When the user profiles something new, pick that workload's few candidate
control levels straight off the already-stored curve, the same way the built-in grid does,
instead of re-running a blind sweep for every new workload.

### Workload Validation Points

There is **no fixed configuration grid**. Calibration is the authoritative frequency/control-space
dataset, and the visualizer is the primary way to explore it. This avoids throwing away measured
information merely to fit a predetermined 12-row matrix.

The execution layouts remain the same:

| Layout | Allocation | Workers |
|---|---|---:|
| A | Four verified higher-performance physical cores, one SMT sibling each | 4 |
| D | All four efficient-class physical cores, one SMT sibling each | 4 |
| B | All eight physical cores, one SMT sibling each | 8 |
| C | All sixteen logical CPUs | 16 |

If class identification is unavailable, use a documented four-physical-core mask and label it accordingly.

The Profile Explorer displays performance, energy, efficiency, runtime, power, and uncertainty
against the measured control points. A selected point carries its exact accepted control settings
into workload validation.

The UI may provide convenience markers such as **Stock**, **Minimum energy**, **Maximum performance**,
**Best performance/W**, **knee**, and **Pareto frontier**. These are derived from measured data and
are optional suggestions only. They do not form a mandatory grid and do not replace the underlying curve.

When multiple points are selected, deduplicate settings that resolve identically after per-policy
clamping/readback. Workload validation then runs only the selected points. If the user wants a broad
validation sweep, they can select a range or all measured points subject to an explicit workload-validation budget.

The optimizer therefore has two distinct stages:

1. **Characterization:** measure the machine-level control curve for as long as the user permits.
2. **Validation/optimization:** use the visualizer and deterministic selector to choose measured points for the actual workload.

This separation prevents an arbitrary fixed grid from becoming the bottleneck while keeping expensive
workload execution finite and user-controlled.

Control settings remain **(boost, cap) pairs per machine** (or **(boost, EPP-tier) pairs** where caps
are ineffective). Write caps per cpufreq policy, verify actual effect under load, record accepted
values, and snapshot/restore the global boost knob where it exists. Keep governor, EPP, and boost policy
fixed during a cap sweep.
### Include a Fair Baseline

Measure the machine’s captured normal configuration with normal build parallelism, including SMT where appropriate.

Do not call it “Maximum Performance” unless that preset was actually measured and documented.

Recommended comparison cards:

1. **Default baseline**
2. **Lowest energy overall**
3. **Selected within budget**

The second may miss the deadline. That explains the product without inventing a “Power Saver” baseline.

---

## 5. Measurement Protocol

This is the core engineering work.

### Per-Run Lifecycle

```text
Check environment
    ↓
Prepare identical workload state
    ↓
Apply configuration and verify readback
    ↓
Settle under a consistent temperature/idle policy
    ↓
Read energy counter + monotonic timestamp
    ↓
Launch workload as the ordinary user
    ↓
Wait for complete workload termination
    ↓
Read energy counter + monotonic timestamp
    ↓
Verify successful output
    ↓
Persist measurements and status
```

Preparation and correctness checking are outside the task-energy window, but can be included in a separately measured profiling-session overhead.

Use a monotonic clock for elapsed time.

Record launch/read overhead consistently; do not claim precision finer than the instrumentation supports.

### Repetitions and Order

For each configuration:

- Three profiling repetitions minimum.
- Randomized configuration order within each pass.
- Baseline checks distributed through the session.
- Median and observed range retained.
- Failed runs, timeouts, and deadline misses retained—not silently discarded.

A configuration with unexplained failures should be marked unstable/ineligible, not repeatedly retried until it gets three flattering successes.

Workload validation cost now depends on the number of points the user selects. The UI must show an execution-time estimate before starting a multi-point validation run, including repetitions, settling, preparation, and validation. This is on top of the one-time Calibration Sweep (§4), whose duration is separately chosen by the user.

The full sweep is preparation material, not the live presentation.

### Energy-Counter Handling

For a wrapping counter with advertised range $R$:

$$
\Delta E_i = (E_i - E_{i-1}) \bmod R
$$

Sum incremental deltas and apply the backend’s unit conversion.

Periodic reads are needed when more than one wrap could occur between start and finish. Choose the sampling interval from the counter’s range and a conservative plausible power ceiling.

Also:

- Deduplicate sysfs aliases.
- Sum independent package domains only.
- Detect counter resets, unavailable reads, suspend/resume, and backend failures.
- Never report missing energy as zero joules.
- Do not subtract an invented idle baseline.

The metric is:

> **Hardware-reported CPU-package energy during workload execution.**

It is not process energy, RTX energy, or wall-outlet consumption.

### Quiet Measurement Mode

During profiling and validation:

- No LLM generation.
- No model loading.
- No unnecessary animations.
- Low-rate progress updates.
- No concurrent experiments.
- Stable AC/platform power state.
- Consistent cooling conditions.

Prefer viewing the dashboard from another machine through an SSH tunnel. If the same laptop is used, keep its browser workload consistent.

Even GPU inference can affect CPU activity, cooling, and platform power allocation.

---

## 6. Deterministic Optimizer

**No ML model is required to calculate the recommendation.**

The deterministic selector is exact **over the user-selected measured candidate set**. If the user selects all measured points, selection is exhaustive over that measured set.

### Deadline Mode

For configuration $c$:

- $E_c$: median valid profiling energy.
- $T_c$: median valid profiling runtime.
- $T_{\text{guard},c}$: conservative runtime estimate.

A practical MVP rule is:

$$
T_{\text{guard},c}
=
\max(T_{c,1}, T_{c,2}, T_{c,3})(1+m)
$$

Here, $m$ is a visible headroom setting, such as 5%.

Then:

$$
c^*
=
\arg\min_c E_c
\quad \text{subject to} \quad
T_{\text{guard},c} \le D
$$

This headroom is a **heuristic**, not a statistical confidence interval or real-time guarantee. Three repetitions do not establish a reliable p95 runtime.

#### Selection Pseudocode

```python
from statistics import median


def select_configuration(configs, deadline_s, margin=0.05):
    eligible = [
        c
        for c in configs
        if c.profile_is_usable
        and max(c.runtime_samples) * (1 + margin) <= deadline_s
    ]

    if not eligible:
        return NoFeasibleConfiguration()

    return min(
        eligible,
        key=lambda c: (
            median(c.energy_samples),
            max(c.runtime_samples),
            c.id,
        ),
    )
```

The product claim should be:

> Lowest-energy measured configuration meeting the selected empirical runtime rule.

Not:

> Guaranteed optimal CPU configuration.

### Frontier Mode

Show non-dominated configurations: no other point is both faster and lower-energy, with at least one strict improvement.

Highlight:

- Fastest measured configuration.
- Lowest-energy measured configuration.
- The tradeoff frontier.

There is no need for a separate “AI efficiency solver.”

For equivalent fixed work:

$$
\frac{\text{performance}}{\text{average power}}
=
\frac{1/T}{E/T}
=
\frac{1}{E}
$$

Performance-per-watt is another way to present energy per task, not an independent discovery.

### Required Edge States

Implement these deliberately:

- No configuration meets the deadline.
- No meaningful improvement over baseline.
- Selected result is within observed measurement variation.
- Profile exists but has not been freshly validated.
- Environment has changed since profiling.
- Energy measurement unavailable.
- Workload failed.
- Validation missed the deadline.

Do not force a green success state.

---

## 7. Fresh Validation

After profiling:

1. Freeze the candidate and runtime budget.
2. Run fresh baseline/selected pairs.
3. Alternate or randomize order.
4. Preserve all results.

For prepared evidence, aim for **three fresh pairs**.

For the live presentation, run **one additional pair** and display it separately from the prepared repeated validation.

```text
Profiling results:
    Used to choose the configuration

Validation results:
    Not used to choose it

Live pair:
    Additional execution, visibly labeled
```

If validation fails, report the failure.

If the candidate changes after seeing validation results, the replacement needs new independent validation.

### Compute Comparisons in Code

$$
\text{energy reduction}
=
100\left(
1 - \frac{E_{\text{selected}}}{E_{\text{baseline}}}
\right)
$$

$$
\text{runtime increase}
=
100\left(
\frac{T_{\text{selected}}}{T_{\text{baseline}}} - 1
\right)
$$

For aggregate comparisons, specify that these use validation medians and show observed ranges.

Use wording such as:

> All three fresh validation runs finished within the budget.

That is more precise than implying every future execution is guaranteed to do so.

---

## 8. Implementation Architecture

### Recommended Stack

| Component | Choice |
|---|---|
| Core/harness | Python 3 |
| API | FastAPI |
| CLI | Typer |
| Frontend | React + TypeScript + Vite |
| Chart | Plotly scatter chart |
| Persistence | SQLite + JSON export |
| Progress updates | Server-Sent Events |
| Privileged operations | Small root-owned helper over a Unix socket |
| Local explanation | One tested llama.cpp-compatible endpoint |
| Cloud explanation | Generic OpenAI-compatible adapter |

No Redis, Celery, Kubernetes, vector database, or training pipeline.

### Architecture

```text
React dashboard / CLI
          │
          ▼
Unprivileged application
  ├── Capability discovery
  ├── Experiment state machine
  ├── Workload runner
  ├── Measurement orchestration
  ├── SQLite persistence
  ├── Deterministic optimizer
  └── Explanation service
          │
          ├── Basic templates
          ├── Local LLM
          └── Opt-in cloud endpoint

          │ narrow Unix-socket API
          ▼
Privileged helper
  ├── Snapshot approved CPU settings
  ├── Apply validated settings
  ├── Read privileged energy source
  ├── Session lease/watchdog
  └── Restore original state
```

**The LLM has no path to privileged control.**

### Repository Layout

```text
joulectrl/
├── core/
│   ├── discovery.py
│   ├── topology.py
│   ├── calibration.py
│   ├── watch.py
│   ├── controller_client.py
│   ├── experiment.py
│   ├── runner.py
│   ├── optimizer.py
│   ├── validation.py
│   └── models.py
├── energy/
│   ├── base.py
│   └── verified_backend.py
├── workloads/
│   ├── base.py
│   ├── clean_build.py
│   └── fixed_compute.py
├── explain/
│   ├── facts.py
│   ├── templates.py
│   └── providers.py
├── helper/
├── api/
├── cli/
├── frontend/
├── tests/
├── demo/
└── .github/workflows/ci.yml
```

Do not build three energy backends before one works.

### Workload Plugin Contract

```python
class Workload:
    def prepare(self, run_context):
        ...

    def command(self, workers) -> list[str]:
        ...

    def environment(self, workers) -> dict[str, str]:
        ...

    def verify(self, run_context) -> bool:
        ...

    def fingerprint(self) -> dict:
        ...
```

Run commands using argument arrays, not shell interpolation.

For the MVP, affinity can be applied with an unprivileged `taskset` invocation around the approved workload command.

Track the process group so cancellation terminates the complete build, not just its parent process.

### Experiment State Machine

```text
IDLE
 → CHECKING
 → PREPARING
 → PROFILING
 → PROFILE_READY
 → SELECTED
 → VALIDATING
 → COMPLETE
```

Any active state can transition through:

```text
CANCELLING / FAILED
 → RESTORING
 → RESTORED / RECOVERY_REQUIRED
```

Store state transitions. The dashboard should never guess whether restoration happened.

### Minimal API

```text
GET  /api/capabilities
GET  /api/workloads

POST /api/experiments
GET  /api/experiments/{id}
GET  /api/experiments/{id}/events

POST /api/experiments/{id}/select
POST /api/experiments/{id}/validate
POST /api/experiments/{id}/cancel

POST /api/restore
POST /api/explain

GET  /api/experiments/{id}/export
```

Changing the deadline only reruns selection against existing data. It does not rerun the workload.

### Data to Persist

#### Experiment

- CPU/kernel/driver/topology fingerprint.
- Workload source and input fingerprint.
- Compiler/build flags.
- Original power settings.
- Energy backend and domain.
- AC/platform profile.
- Randomization seed.
- Start/end timestamps.

#### Configuration

- Exact CPU mask.
- Worker count.
- Requested and accepted per-policy caps or EPP values.
- Fixed governor/boost settings.

#### Run

- Profile versus validation versus live-demo phase.
- Runtime and energy.
- Raw counter information needed for auditing.
- Exit code and correctness status.
- Timeout/cancellation.
- Available temperature/context telemetry.
- Warnings.

This enables a defensible downloadable result, not just a screenshot.

---

## 9. Privilege and Restoration Design

**Do not run FastAPI, the browser, the LLM server, or compilation as root.**

The helper should accept a small operation set:

```text
begin_session
read_energy
apply_configuration
heartbeat
restore
end_session
```

It must not accept:

- Arbitrary shell commands.
- Arbitrary executable paths.
- Arbitrary sysfs paths.
- Arbitrary file writes.

Validate setting ranges against discovered policy capabilities.

### Required Safety Behavior

1. One exclusive experiment lease.
2. Authenticate the local client using Unix-socket peer credentials.
3. Persist a root-owned recovery snapshot **before changing settings**.
4. Apply min/max changes in an order that maintains valid bounds.
5. Read back accepted settings.
6. Restore after completion, cancellation, and handled errors.
7. Restore if the client heartbeat disappears.
8. Provide `joulectrl restore` for recovery.
9. Verify restoration and report failure explicitly.

Include the boot ID and hardware fingerprint in recovery state. Do not blindly replay an old snapshot after reboot or onto another system.

A watchdog improves recovery from application crashes but cannot guarantee recovery from every kernel or power failure. The recovery file and manual command remain necessary.

### Web Boundary

- Bind to `127.0.0.1`.
- Serve frontend and API from one origin.
- Use origin checks and a session token for state-changing operations.
- Access remotely through an SSH tunnel for the event.
- Never store cloud API keys in frontend code.

---

## 10. Explanation Layer

> **Basic explanations are the default guaranteed capability. A local 7B model is an enhancement, not an installation requirement.**

### Provider Selector

```text
Explanation provider

● Basic — offline, no model required
○ Local model — user-selected endpoint/model
○ Cloud API — explicit opt-in
```

If an LLM fails or times out, fall back to Basic.

**Do not silently send data to the cloud.**

### Basic Explanation

Generate explanations from deterministic facts:

```text
The selected configuration had the lowest median package energy
among measured configurations meeting your runtime rule.

The lowest-energy overall configuration was excluded because
its guarded runtime exceeded your budget.

Fresh validation completed within the budget in 3 of 3 runs.
```

Populate numerical comparisons from the same code that renders the dashboard.

This is sufficient for the complete product.

### Local Model Recommendation

For the event, support one path first:

- `llama.cpp` server.
- A 7B instruct GGUF, such as a suitable Qwen2.5-7B-Instruct quantization.
- Q4-class quantization.
- 2K–4K context.
- One request at a time.
- Approximately 150–250 output tokens.

Confirm the model’s license and the exact runtime’s GPU support.

Example, after verifying the CUDA build and driver:

```bash
llama-server \
  -m /path/to/model.gguf \
  -ngl 99 \
  -c 4096 \
  --host 127.0.0.1 \
  --port 8081
```

If memory is tight:

1. Reduce context.
2. Use a smaller 3B-class model.
3. Partially offload or use CPU inference after measurements.
4. Use Basic explanations.

“Most machines can run it” should not be the compatibility claim. Many can run a quantized model with sufficient system RAM, but usable latency and available memory vary.

### Cloud Support

A simple OpenAI-compatible chat-completions adapter can cover many local servers and cloud gateways, with small provider-specific adjustments.

User supplies:

```text
Base URL
Model identifier
API key
```

Send only required structured facts:

- Deadline.
- Selected configuration label.
- Measured summaries.
- Computed comparisons.
- Rejection reasons.
- Validation status.
- Caveats.

Exclude source code, workload contents, raw logs, sensitive paths, and machine identifiers by default.

### Grounding Rules

The LLM may explain the evidence. It may not:

- Select or apply settings.
- Invent measurements.
- Compute authoritative percentages.
- Claim a hardware cause not established by the experiment.
- Promise a future deadline.

Canonical numerical cards come directly from code.

Suggested questions:

- “Why was this configuration selected?”
- “Why not use all logical CPUs?”
- “What changes if I allow more time?”

The final question should call the deterministic selector with another budget and then explain the result—not ask the model to guess.

**Load and run the model only after the measurement sequence. Before another benchmark, stop generation and allow the machine to return to its measurement conditions.**

---

## 11. Dashboard and User Flow

Keep the dashboard to three views.

### A. Setup

```text
Workload:              Clean build
Objective:             Finish within budget
Runtime budget:        [ slider + number + Unlimited ]
Calibration budget:    [ slider + number + Unlimited ]
Validation points:    [ select from curve / range / all ]
Calibration quality:   [ estimated minimum + warning if below floor ]
Runtime headroom:      [ visible setting ]

Hardware:
Package-energy access  ✓
CPU controls           ✓
Restoration available  ✓

[ Profile workload ]
```

If something is unavailable, state exactly which functionality is reduced.

### B. Profile Explorer

Main graph:

- X-axis: runtime in seconds.
- Y-axis: package energy in joules.
- Twelve configuration summary points.
- Each point labeled as median of three runs.
- Color by execution layout.
- Hover with CPU mask, workers, cap/EPP, and spread.
- Deadline line.
- Pareto frontier.
- Selected candidate.

Show actual runtime ranges and the guarded-runtime marker used for eligibility. Otherwise, a point may appear left of the deadline while the conservative selector rejects it.

The frontier is descriptive; the selector should still check all usable configurations.

Comparison cards:

```text
Default baseline
Lowest energy overall
Selected within budget
```

Status should distinguish:

```text
Predicted from profile
Fresh validation available
Live validation running
Deadline missed
No measurable improvement
```

### C. Validation and Explanation

```text
[ Validate with fresh runs ]

Baseline              Selected
Runtime               Runtime
Package energy        Package energy
Correctness           Correctness
```

Below:

- Observed savings.
- Runtime difference.
- Deadline outcomes.
- Measurement spread.
- Explanation provider.
- Export button.
- Restore status.

Permanent footer:

> CPU-package energy, not whole-system electricity. Best among measured configurations; future runtimes may vary.

---

## 12. Compatibility Strategy

**Architect for broad Linux support; certify capabilities individually.**

| Tier | Available capability | Product behavior |
|---|---|---|
| Full | Package energy + effective frequency/EPP control + affinity | Full optimization |
| Reduced control | Package energy + affinity/thread control | Optimize execution layout |
| Measurement only | Package energy, limited control | Compare approved workload variants/configurations |
| Timing only | No package-energy source | Runtime profiling; energy optimization disabled |
| Replay | Saved real experiment | Clearly labeled exploration, no live-control claim |

Distribution support is easier than hardware support. Linux distributions share kernel interfaces, but permissions, services, kernel versions, and exposed counters differ.

Containers and VMs may lack host controls and host energy counters. Do not claim transparent support there.

### Profile Validity

Profiles are workload-and-environment-specific.

Invalidate or require revalidation after material changes to:

- Workload/input.
- Toolchain.
- CPU/machine.
- Kernel/driver.
- Power policy.
- AC/battery conditions.

Do not transfer a winning setting from one laptop to another as though it were universal.

---

## 13. Implementation Schedule: 36 Hours, Four People

### Ownership

| Person | Primary ownership |
|---|---|
| A | Linux discovery, energy backend, controller helper, restoration |
| B | Harness, database, optimizer, validation, core API |
| C | Dashboard, graph, progress, error states |
| D | Workloads, integration tests, explanation adapter, demo/pitch |

Person D’s priority is **workload reliability before LLM polish**.

### Hours 0–4: Prove the Physical Experiment

- Verify topology.
- Verify package energy.
- Verify one effective control.
- Complete one correct workload run.
- Restore original state.
- Fix shared data/API schemas.
- Add the CI workflow (install + unit tests on push) — it is the only per-push guard while everyone merges directly to main.

**Gate:** real runtime and joules from a correct execution.

If energy is unavailable, make the contingency decision now.

### Hours 4–8: First End-to-End Result

- CLI runner works.
- One result persists.
- Dashboard displays that real result.
- Cancellation terminates the process group.
- Restoration is visible.
- Basic explanation works.

**Gate:** UI → workload → measurement → stored result → UI.

### Hours 8–16: Complete the Core Loop

- Twelve-configuration sweep.
- Repetitions and randomized order.
- Deadline selection.
- Pareto chart.
- Apply/restore.
- Export.
- Basic failure states.

**Gate:** an entire profile produces a reproducible selection.

### Hours 16–24: Evidence and Independent Validation

- Finish the full profile.
- Run fresh validation pairs.
- Investigate drift or instability.
- Prepare the contrasting workload.
- Add profiling-overhead accounting.
- Test the local LLM only now.

**Gate:** honest evidence exists, whether it shows savings or not.

### Hours 24–30: Polish

- Provider selector.
- Optional cloud endpoint.
- Useful explanations.
- Recovery tests.
- Replay mode.
- Screenshots/video.
- Pitch rehearsal.

### Hours 30–36: Freeze and Rehearse

No new tuning dimensions or inference backends.

- Rehearse the live pair.
- Confirm AC/power/thermal conditions.
- Save final raw data.
- Check restore recovery.
- Prepare offline assets.
- Rehearse no-savings and live-failure explanations.

Where event rules permit, download compilers, source dependencies, model weights, and GPU runtime assets beforehand. Respect rules on prebuilt code and pre-event work.

---

## 14. Tests That Matter Most

### Optimizer Tests

- Lowest-energy feasible point selected.
- Lower-energy but late point rejected.
- No feasible point.
- Baseline already optimal.
- Tie behavior deterministic.
- Guarded runtime differs from median.
- Invalid/unstable profiles rejected.
- Frontier dominance correct.
- Percentages correct.

### Measurement Tests

- Counter unit conversion.
- Single wrap.
- Multiple incremental reads.
- Counter reset/unavailable.
- Missing energy never becomes zero.
- Workload fails correctness.
- Timeout.
- Child process outlives parent.

Use synthetic counters in unit tests, clearly separate from demo measurement data.

### Safety Tests

- Cancel mid-build.
- Kill the unprivileged application.
- Disconnect UI.
- Attempt a second experiment.
- Reject an out-of-range cap.
- Detect a conflicting policy change.
- Restore every touched setting.
- Recognize stale recovery data.
- LLM endpoint failure leaves optimization fully functional.

### Definition of Done

The hard MVP is complete when:

> A user can profile an approved workload, choose a runtime budget, inspect the selected measured configuration, validate it on fresh executions, export the evidence, and have the machine restored—even with all LLM functionality disabled.

---

## 15. Profiling Overhead and Business Story

Measure energy consumed by the dedicated profiling/validation session where practical, including preparation and settling.

Keep task-window energy and session overhead separate.

For recurring workloads:

$$
N_{\text{break-even}}
=
\left\lceil
\frac{E_{\text{extra profiling}}}{E_{\text{baseline}} - E_{\text{selected}}}
\right\rceil
$$

Only show a break-even estimate when observed savings are positive and repeatable enough to support one.

Label it:

> Estimated CPU-package energy payback, assuming future executions resemble validation.

Do not convert package joules directly into promised electricity-bill reductions.

### Pitch Direction

> For one build, the savings may be small. For a dedicated runner executing the same job thousands of times, profiling once and reusing a validated policy can become worthwhile.

Initial commercial audience:

- Self-hosted CI runners.
- Dedicated build machines.
- Encoding workers.
- Repeatable batch-compute systems.

Free local utility first; paid policy management, revalidation, reporting, and integration later.

Keep telemetry sales out of the event pitch.

---

## 16. Five-Minute Demo

### 0:00–0:30 — Problem

> Low power is not the same as low energy. We ask: what measured settings finish this job on time with the least CPU-package energy?

### 0:30–1:15 — Show the Profile

Show the real dataset:

```text
Previously measured on this machine
Same source, same build target, repeated runs
```

Move the deadline slider. Let the selection change immediately.

### 1:15–2:45 — Fresh Comparison

> These measurements selected the candidate. Now we test it on executions that were not used to select it.

Run baseline and selected configuration live.

### 2:45–3:30 — Show Results

Show:

- Correctness.
- Runtime.
- Package energy.
- Budget outcome.
- Prepared validation ranges.
- The additional live pair.

Do not overwrite repeated evidence with the most flattering live result.

### 3:30–4:00 — Explanation

Ask why the configuration was selected.

Show that Basic mode works even if the local model is unavailable.

### 4:00–4:30 — Workload Dependence and Reversibility

Show the second prepared workload if useful, then:

```text
Original CPU settings restored ✓
```

### 4:30–5:00 — Future Customer

Explain recurring dedicated compute, amortized profiling, and transparent evidence.

Have a clearly labeled real-data replay and short recorded run ready.

---

## 17. Authoritative Implementation References

These references help guide implementation. They do not confirm that the exact laptop exposes every feature.

- [Linux AMD P-state documentation](https://docs.kernel.org/admin-guide/pm/amd-pstate.html)
- [Linux CPU frequency scaling documentation](https://docs.kernel.org/admin-guide/pm/cpufreq.html)
- [Linux powercap documentation](https://docs.kernel.org/power/powercap/powercap.html)
- [Linux hwmon documentation](https://docs.kernel.org/hwmon/index.html)
- [llama.cpp](https://github.com/ggml-org/llama.cpp)

---

## Final Positioning

> **`joulectrl` experimentally maps a repeatable Linux workload’s CPU energy/runtime tradeoff, selects the lowest-energy measured configuration within a runtime budget, and checks that selection with fresh runs. It works without AI; optional local or cloud AI makes the evidence easier to understand.**

### Build Order

```text
Hardware proof
    ↓
Safe measurement
    ↓
Deterministic selection
    ↓
Fresh validation
    ↓
Dashboard polish
    ↓
Optional LLM
```

**That ordering gives the team a credible product even if GPU inference fails—and prevents a polished explanation layer from hiding an unverified hardware experiment.**