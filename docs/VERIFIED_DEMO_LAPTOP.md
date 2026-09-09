# VERIFIED_DEMO_LAPTOP.md — pre-verified hardware facts (Sep 9, 2026)

> **Scope:** everything below describes ONE machine — the Fedora demo laptop hosting Agents
> A and B. It is *input to* `joulectrl doctor`'s discovery, not a substitute for it. The
> product stays machine-agnostic (PLAN §12 compatibility tiers): discover policies, classes,
> controls, and energy backends per machine; test each control's actual effect (Gate B);
> degrade honestly. Nothing here may be hardcoded. Where this machine differs from the
> generic assumptions in PLAN §2/§3, the deltas below are flagged so Agent A re-confirms
> instead of rediscovering — on any OTHER machine, run the full Gate A/B procedure.

All findings below were measured on the actual Fedora demo laptop (the machine that will host
Agents A and B) the day before the event, with root via pkexec. Every touched setting was
restored after testing (verified: boost=1, scaling_max_freq=5090000, EPP=performance).
This file replaces *guesswork* about THIS machine with measurements. Agent A: fold these into
`fixtures/real/capability_report.json` at hour 0 and re-confirm each in one pass — do not
re-derive from scratch.

## CPU — AMD Ryzen AI 7 350 w/ Radeon 860M

- 8 cores / 16 threads / 1 socket. SMT sibling pairs: (0,8), (1,9), (2,10), … (7,15).
- **Core classes are directly exposed by cpufreq — no guessing needed:**
  - `cpuinfo_max_freq = 5090910` on even logical CPUs (0,2,4,6,8,10,12,14) → the four
    **Zen 5** cores (physical cores 0,2,4,6).
  - `cpuinfo_max_freq = 3506494` on odd logical CPUs (1,3,5,7,9,11,13,15) → the four
    **Zen 5c** cores (physical cores 1,3,5,7).
  - C1 single-core (stock-only) calibration still runs — it validates the map empirically and
    gives the baseline C2's scaling-efficiency number divides by. The layout-A/D masks are known
    up front regardless: fast = CPUs {0,2,4,6}+siblings, efficient = {1,3,5,7}+siblings. The
    actual perf/watt curve now comes from C2's dense sweep (AGENTS.md §6), not from C1.
- Driver: `amd-pstate-epp`, governor `performance`, `amd_pstate/status = active`.
- **16 per-CPU cpufreq policies (policy0…policy15, one per logical CPU)** — NOT one shared
  policy. Caps must be written per-policy (16 writes per control level). Readback per policy.

## Package energy — VERIFIED WORKING

- Backend: powercap sysfs. `/sys/class/powercap/intel-rapl:0/energy_uj` (yes, the kernel
  names it intel-rapl even on this AMD CPU — the powercap framework's generic naming).
- Domain: `package-0`. Only one package.
- Counter range: `max_energy_range_uj = 65532610987` (~65.5 kJ). At the measured ~52 W
  under load that wraps every ~22 min; at ~12 W idle ~1.6 h. Periodic reads every few
  seconds are more than enough; use the modulo-wrap delta math from PLAN §5.
- Sanity: idle delta ≈ 8.1 mJ over 1 s (~8–12 W package idle); ~52 W under 4-thread
  sha256 load. Counter advances monotonically, no reset observed during tests.
- **Permissions: root-only (`-r--------` root root).** Unprivileged reads are impossible.
  The privileged helper therefore reads energy too — `read_energy` is not optional plumbing.
- `perf` is not installed on this machine (`perf list` unavailable). Do not count on the
  perf RAPL route; powercap is the verified backend. (If desired later: `dnf install perf`,
  but AMD RAPL perf event exposure is unverified — powercap already works.)

## Frequency caps — WORK ONLY WITH BOOST OFF (this machine)

- Writing `scaling_max_freq` as root: write succeeds, readback matches — **but the actual
  frequency ignores the cap while `/sys/devices/system/cpu/cpufreq/boost = 1`**
  (cur_freq stayed ~5.04 GHz with a 2 GHz cap and a busy thread pinned to that CPU).
- With **boost=0**, the same 2 GHz cap is honored: `scaling_cur_freq ≈ 1.99 GHz` observed.
- This boost-vs-cap interaction is machine/driver behavior (amd-pstate-epp here), not a
  universal rule — on other machines, Gate B's busy-thread actual-effect check decides
  whether caps bind at stock boost state.
- Consequence for the workload validation UI HERE: there is no fixed three-control-level grid; the measured curve is exposed directly, and selected points use
  **(boost, cap) pairs** — stock (boost=1, no cap), then two more read off C2's calibration
  curve (AGENTS.md §6) once it has run, not fixed at ~85%/~70%. A cap-only sweep with boost=1
  measures nothing on this machine. Since this driver (amd-pstate-epp) exposes a continuous cap
  range rather than a discrete frequency list, the calibration sweep here lands in ladder tier 2
  (PLAN §4): N evenly spaced cap values (boost=0) between each class's verified min and max,
  sized to fit the ~10–15 minute budget — not a literal enumeration of "every frequency," which
  isn't a meaningful concept on a continuous-range driver.
- `boost` is a single global sysfs knob (`/sys/devices/system/cpu/cpufreq/boost`) —
  snapshot and restore it with everything else.

## EPP — DEAD ON THIS MACHINE (check per machine elsewhere)

- `energy_performance_available_preferences` contains exactly one value: `performance`
  (on every policy). Writing another value is rejected (readback stays `performance`).
- **On this laptop there is no EPP control dimension.** On other machines EPP may work
  fine — the general fallback order in PLAN §3/Gate B (caps → EPP → affinity-only) stands;
  this machine just falls through to caps+affinity. Do not burn hours on EPP HERE.

## Conflicting daemons — CONFIRMED PRESENT

- `tuned` + `tuned-ppd` are both running; active profile `throughput-performance`.
  `nvidia-powerd` and `upower` also running.
- During short tests tuned did not overwrite our caps (readback held), but the
  conflicting-policy detection in PLAN §3/Gate B is a real requirement, not a formality:
  watch for tuned re-applying `throughput-performance` over long measurement windows.
- Do NOT stop tuned for the event without human decision (PLAN §3 rule: explicit,
  recorded, restored). If caps are races mid-sweep, ask the human about
  `tuned-adm profile` switch rather than fighting it in code.

## GPU

- NVIDIA GeForce RTX 5050 Laptop GPU, 8151 MiB — matches PLAN §2's 8 GB assumption
  (7–8B Q4 local-LLM plan is plausible; verify llama.cpp CUDA when actually tested, Gate 4).

## Demo-laptop environment notes

- Fedora (kernel 7.1.10-200.fc44), GNOME/Wayland. `pkexec` works for privileged steps
  (GUI auth prompt); agents propose, humans execute.
- Battery + AC both present (`BAT0` hwmon + `ACAD`) — keep it on AC for all measurements.

## Hour-0 re-verification checklist for Agent A (should take ~10 min)

1. Re-read `energy_uj` twice 1 s apart (root) — advances?
2. Re-confirm class map via `for p in /sys/devices/system/cpu/cpufreq/policy*/; do echo "$(basename $p) $(cat $p/cpuinfo_max_freq)"; done`.
3. One cap+boost=0 test with busy loop pinned to one CPU; confirm cur_freq ≤ cap; restore.
4. Confirm tuned profile unchanged; note AC status.
5. Write `fixtures/real/capability_report.json` with these results and post `[gate1]` line.
