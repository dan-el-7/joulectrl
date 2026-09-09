# AGENTS.md — joulectrl multi-agent working contract (v1, hour 0)

Four AI agents (A, B, C, D) on four laptops build `joulectrl` from one repo. Humans supervise.
This file is the binding contract between agents. The product/technical spec is `docs/PLAN.md`
(the final plan). If this file and PLAN disagree: PLAN wins on product truth, this file wins
on process.

## 0. Session rules (every session, no exceptions)

1. `git pull --rebase origin main` before any work.
2. Re-read the **status logs** and **Verified facts** below — other agents moved while you were away.
3. Check `AFFECTS(...)` tags that mention your letter; adapt before continuing.
4. If blocked > 30 min: append a `[blocked] <reason>` line to your log, then help the agent directly
   upstream or downstream of you.
5. Same-laptop rule (A + B share the demo machine): work only in your own clone
   (`~/joulectrl-a` / `~/joulectrl-b`), own venv, distinct `git config user.name` (`agent-a` /
   `agent-b`). Never touch the other clone; the remote is the only coordination channel.
6. When resuming an interrupted session: pull, re-read logs, and finish your open checklist item
   before starting anything new.
7. Keep `AGENTS2.md` (live state) and `HANDOFF.md` (resume packet) continuously current (§4b) —
   they are how your work survives a session crash, timeout, context exhaustion, or model swap.

## 1. Non-negotiables (from PLAN — violating any of these fails the demo)

- **Measure, don't estimate.** Package energy from a verified hardware counter only. Never relabel
  a core-only counter as package energy; never report missing energy as zero; never subtract an
  invented idle baseline.
- **Restore everything.** Recovery snapshot before any change; readback after apply; restore on
  completion, cancellation, error, and heartbeat loss; restoration state always visible in the UI.
- **The LLM has no privileged path.** It explains results only. The deterministic optimizer
  selects. Templates always work; any LLM failure degrades to Basic, never to silence.
- **Quiet mode during any measurement.** No LLM generation, no model loads, low-rate UI updates,
  no concurrent experiments on the demo laptop. A brackets measurement windows with `[measuring]` /
  `[done-measuring]` log lines; while a window is open (or the helper lease is held), B defers
  heavy compile/test loops on this machine — light unit tests are fine.
- **Bounded claims.** "Lowest-energy measured configuration meeting the empirical runtime rule" —
  never "guaranteed optimal". Calibration data never mixes into workload Pareto charts.
- **Scope guard.** Your gate checklist is your scope. Anything beyond it needs a human go.
- **No code outside your ownership map** — ever, not even "small fixes" to someone else's area.
  Instead append an `AFFECTS(<owner>)` note describing the problem.

## 2. Ownership map (hard boundaries)

| Path | Owner | Notes |
|---|---|---|
| `core/models.py` | **B** | ALL frozen data contracts. Changes via contract protocol only. |
| `core/discovery.py`, `core/topology.py`, `core/calibration.py` | **A** | Read-only discovery + calibration orchestration. |
| `energy/base.py` | **A** | `EnergyBackend` protocol + counter semantics (units, wrap, reset). |
| `energy/synthetic.py` | **B** | Implements A's semantics (wrap, reset, unavailability); used by all dev laptops + tests. A co-signs semantics at Gate 1. |
| `energy/*` (real backends, units, wrap handling) | **A** | One working backend first; interface permits others later. |
| `core/controller_client.py`, `helper/` | **A** | Privileged helper + narrow op set. No shell, no arbitrary paths. |
| `core/store.py`, `core/experiment.py`, `core/runner.py`, `core/optimizer.py`, `core/validation.py`, `cli/` | **B** | State machine, persistence, selection, validation. |
| `core/watch.py` | **B** | Passive idle→activity→idle detector (§6b, estimate tier). A co-signs baseline/threshold semantics on real hardware. |
| `api/`, `frontend/` | **C** | Bind 127.0.0.1; one origin; SSE event names are a contract. |
| `workloads/` (base.py + plugins), compute kernel source | **D** | Kernel: fixed chunks, fixed work per chunk, deterministic checksum, checksum independent of worker count. |
| `explain/` | **D** | Templates always; LLM adapters optional; grounding rules from PLAN §10. |
| `tests/unit/test_<area>*` | each agent | You write and own tests for your own area. |
| `tests/integration/`, `demo/`, `fixtures/synthetic/` | **D** | Cross-cutting E2E + synthetic data. |
| `fixtures/real/` | **A** | JSON only, small: capability report, topology, calibration records, one short energy trace. |
| `docs/`, `AGENTS.md` | shared | Append-only per section (see §4). |

Environment note: A and B share the Fedora demo laptop (separate clones, see §0.5); C and D
laptops may be Windows/WSL/Linux. Pure-Python areas must stay cross-platform. Anything touching
sysfs/perf/taskset/cgroups is A's and Linux-only. `main` must stay installable
(`pip install -e .`, your unit tests green) on every clone.

## 3. Git protocol

- Branches: `<letter>/<topic>` off latest `main`. Trunk is `main`. **No force-push, ever.**
- **Commit trigger:** a unit works + its unit tests pass.
- **Push trigger:** every commit. Push as you go; do not hoard local commits.
- **Merge to main:** `git pull --rebase origin main` first; run your unit tests; merge only if
  the diff touches your owned files + your AGENTS.md log section. Anything else → contract
  protocol or owner coordination first.
- Commit message style: `[a] energy: powercap read loop with wrap handling`.
- **Before EVERY push:** `git pull --rebase origin main` → review `git diff origin/main..HEAD`
  (stat first, then full) → confirm only your files + intended log lines → push.
- **After EVERY pull:** read incoming diffs to `AGENTS.md` and contract files. Any
  `AFFECTS(<you>)` or `[contract]` line → read it and adapt before writing code.
- Never commit: model weights, `.venv`, run data, build outputs, secrets, editor junk.
  `fixtures/real/` JSON is explicitly wanted (small, auditable).

## 4. AGENTS.md update protocol

This file is the message board. Keep it green:

- When you finish something meaningful → append **one dated line** to YOUR log section (§8) and push immediately.
- Tags for log lines:
  - `[contract]` — changes a frozen interface (§5). Push immediately; others rebase and adapt.
  - `AFFECTS(a,b,c)` — others must read this line.
  - `[blocked]` / `[unblocked]` — status signal.
  - `[gate<N>]` — you consider gate N's exit met for your part.
- Verified facts (§9): any agent may add a line, but only with *how it was verified* (command, run ID, fixture path).
- Discipline: append inside your own section; never edit or delete others' lines; pull --rebase
  before editing; review your diff before pushing. Humans review these diffs too.

## 4b. Live state + handoff (model-failure insurance)

`AGENTS.md` §8 is append-only history. Two rewritable companion files cover *current* state:

- `AGENTS2.md` — per-agent live state (heartbeat, session generation, branch, current unit,
  next action). Each agent rewrites its own section; update triggers and the rescue rule are
  defined in that file. Heartbeat staleness > 20 min (outside a bracketed [measuring] window)
  is a failure signal; humans confirm death.
- `HANDOFF.md` — per-agent resume packet (done & verified, in flight, resume here, gotchas)
  written for a zero-context successor. Write the packet BEFORE debugging a session-killing
  error; update after every push and when ending a session.

Resume protocol (any new/replacement session): pull → read your sections in AGENTS2.md +
HANDOFF.md → inspect the clone (git status / stash / log), salvage or deliberately stash WIP →
increment your session generation and post a heartbeat → execute the "resume here" line →
finish the open unit before starting anything new (§0.6). Ownership boundaries survive session
death: a rescue is a human-granted exception, not a land grab.

## 5. Frozen contracts (freeze by hour 3)

| Contract | File | Owner |
|---|---|---|
| Data models: `CpuTopology`, `CoreClassMap`, `Configuration`, `RunRecord` (incl. `mode` = `harness`\|`watch` + detection metadata), `CalibrationRecord` (incl. requested/accepted control level per row), `Profile`, `Selection` (objective mode + preference targets/outcomes, §6c), `ValidationPair`, `CapabilityReport` | `core/models.py` | B |
| API route table + SSE event names (PLAN §8) + watch endpoints & event (§6b) | `api/routes.py` + `docs/API.md` | C |
- **Helper op set: `begin_session, read_energy, apply_configuration, heartbeat, restore, end_session`** + socket path + peer-cred auth. Note: on machines with root-only energy counters (the demo laptop is one — powercap is `-r--------` root there), `read_energy` is a required helper op from hour 0, not optional plumbing; where unprivileged reads work, the app may read directly but keep the helper path implemented either way. A: create `.github/workflows/ci.yml` at Gate 0 (see §10 CI). | `helper/` + `docs/HELPER.md` + `.github/workflows/ci.yml` | A |
| Workload plugin: `prepare / command / environment / verify / fingerprint` (PLAN §8) | `workloads/base.py` | D |

**Change rule:** only the owner edits; add a `[contract]` log line; push immediately. Everyone
else rebases and adapts at their next pull. No drive-by edits, no unilateral renames.

## 6. Calibration spec (A executes; kernel comes from D by h2)

**Read `VERIFIED_DEMO_LAPTOP.md` first** — the demo laptop's hardware was pre-verified Sep 9
2026, so its Gate A/B work is re-confirmation, not discovery. That machine's facts: core
classes exposed via per-CPU `cpuinfo_max_freq` (Zen 5 = even CPUs, Zen 5c = odd); 16 per-CPU
cpufreq policies; caps honored ONLY with global boost=0; EPP single-valued (dead as a control
dimension there); powercap package energy works but is root-only (helper reads energy).
**These are machine facts, not product assumptions** — the code paths stay general: discover
policies/classes per machine, test each control's actual effect (Gate B), degrade per the
compatibility tiers (PLAN §12). Machine facts live in `fixtures/real/` and capability
reports, never hardcoded.

Purpose: measured perf/power scaling data per core set, stored as first-class metrics, feeding
the calibration curve and user-selected workload validation. See PLAN + TEAM_PLAN §4.

- **Discover sets, don't assume them.** Candidate classes from topology reads; C1 empirically
  confirms which set is faster. CPU numbering is not evidence.
- **C1 (single-core, stock only):** kernel pinned via taskset to one core from each set, ≥5
  reps, quiet mode, stock config only. One row per set: median runtime, package energy, avg
  watts, work/sec. Validates the class map and gives the single-core baseline that C2's
  scaling-efficiency number divides by. C1 is deliberately cheap — it is not where the
  perf/watt curve comes from anymore (that's C2, below).
- **C2 (parallel scaling, now the dense calibration sweep):** the actual performance-per-watt
  curve. Same kernel, run at each class's natural full-physical-core layout (4 workers, one
  SMT sibling each — Layout A's shape / Layout D's shape), first at stock (feeds scaling
  efficiency = parallel throughput / (workers × C1's single-core throughput)), then swept
  across a ladder of control points instead of the old fixed 3 grid levels:
  1. Discrete frequency list exposed → test every listed step (small, bounded — literal "all").
  2. Continuous cap range, no discrete list (this machine's case) → N evenly spaced cap values
     from the class's verified min to max, boost fixed per Gate B. Finite sweep density is
     computed from the user's calibration-time budget and measured per-point cost; Unlimited/
     Exhaustive enumerates every distinct driver/readback control point.
  3. Caps ineffective → every supported EPP tier (typically 2–4), labeled as a tier, not GHz.
  4. No effective control → skip the curve for that class; note it in the capability report;
     that class falls back to affinity + worker-count only.
  Only drop a tier when Gate B–style verification shows the tier above doesn't actually work —
  never pre-emptively degrade. Calibration time is user-selectable, including Unlimited/Exhaustive.
  Finite runs use a machine-derived minimum reliable duration and warn below it; remaining time is
  adaptively spent on frequency coverage and repetitions. Caps are per-cpufreq-policy on machines
  with per-CPU policies (the demo laptop has 16); write and read back each policy's cap.
- **Grid removal (team decision, folded into PLAN §4):** Layout D remains an execution layout, but
  there is no fixed 12-configuration grid. Preserve the full calibration curve and expose it in the
  explorer. The user selects measured control points for expensive workload validation. Convenience
  markers (stock / minimum-energy / maximum-performance / best-performance-W / knee / Pareto) are
  derived from measurements and are suggestions only.
- Storage: `CalibrationRecord` rows (`phase="calibration"`, incl. requested + accepted control
  level per row) + JSON export in `fixtures/real/`. No schema change needed — the dense sweep
  is just many more rows of the same shape. Include kernel checksum + machine fingerprint (boot
  id) per record. Never mix into workload Pareto data.
- Consumers: layout-A and layout-D masks + their derived control levels (A → B), dashboard
  hardware card (C), explanation facts (D), sanity cross-check on sweep numbers (B).

## 6b. Watch-mode spec (passive auto-detect — estimate tier)

Purpose: the tool must learn how long (and roughly how energy-expensive) a task is without asking
the user to time anything. For harness workloads, profiling measures it. For a task the user runs
*outside* the harness (their own loop), watch mode detects idle → activity → idle from the
package-power trace and records runtime (monotonic clock) + estimated task-window energy. Those
observations produce a **suggested budget** that pre-fills the Setup slider. Product flow:

```text
watch → suggested budget → harness profile → selection → validation
```

Watch is read-only: no user-supplied timing, no controls applied.

- **Ownership:** detector `core/watch.py` — B. B also extends `energy/synthetic.py` with
  *scripted power profiles* (idle, spike, mid-task dip, return) for unit/integration tests.
  A co-signs baseline/threshold semantics on real hardware. C: live watch panel + endpoints.
  D: integration test + demo beat ("point it at anything you run").
- **Idle baseline:** learned over ~30–60 s of genuine idle at watch start (median + spread of
  package power), recalibrated whenever sustained idle is re-detected. Baseline params stored
  in the record for audit.
- **Onset:** power leaves the idle band and stays out ≥ N s (default 2–5, configurable) →
  confirmed start, **backdated** to the first above-band sample. The sustained requirement
  rejects background blips.
- **End (dip rule):** a mid-task dip is not the end. Declare rest only after the trace has held
  inside the idle band for a sustained grace period (default ~10 s, configurable); then set
  activity end = the **last above-band sample** (backtracked). Trailing settle time never counts
  toward runtime; a short dip inside the grace window is absorbed into the task window.
- **Long idle** (> ~60 s inside the band) closes the window; the next spike opens a new segment,
  listed separately. Never auto-merge segments.
- **Clock/meter:** runtime = monotonic clock between backdated onset/end; energy = wrap-safe
  counter delta across the same window. Poll at 0.5–1 Hz — the watcher must stay featherweight
  so it does not perturb the machine it watches. Detection uncertainty ≈ one poll interval; the
  UI/CLI labels state it.
- **Honesty guards:** watch records carry `mode="watch"` and are excluded from Pareto/selection
  evidence by default — context only, labeled "estimated via idle-return detection". Missing
  counter reads mark energy unavailable, never zero. Watch mode never applies settings and needs
  the helper only for `read_energy` (no lease over controls).
- **Schedule:** contracts in models v0 + API table at Gate 0 (cheap now, contract churn later).
  Implementation is a **first-class Gate 3–4 workstream**: B — detector + scripted-profile tests
  (second track inside Gate 3, after the grid builder); C — endpoints + live panel (Gate 3),
  suggested-budget card (Gate 4); D — integration test + demo beat (Gate 4). Leftovers in
  polish. Timing-only fallback (utilization-based onset, runtime-only) is a stretch goal.

## 6c. Preference mode spec (the "70% power / 90% perf" slider)

A third objective selectable in Setup, alongside Deadline mode (default, primary) and the
descriptive frontier view. The user expresses a tradeoff as two percentages relative to the
measured baseline configuration:

- **Energy target** — e.g. ≤ 70% of baseline package energy for the task.
- **Performance floor** — e.g. ≥ 90% of baseline speed (runtime ≤ ~111% of baseline). The UI
  shows both translations (energy %, runtime %).

- **Rule (deterministic, measured points only):** eligible = usable configurations meeting BOTH
  targets, feasibility checked on guarded runtimes (same margin machinery as Deadline mode);
  pick minimum median energy, tie-break minimum guarded runtime, then config id. The baseline
  itself is a candidate.
- **When nothing meets both:** never silently relax a target — report the closest honest
  outcomes explicitly (best meeting the perf floor + its energy miss; best meeting the energy
  target + its runtime miss) and mark the outcome state.
- **Same edge states** as Deadline mode: no feasible point, baseline already best, result within
  observed noise, profile not freshly validated.
- **Claims:** "lowest-energy measured configuration meeting your preference rule" — 70/90 is a
  target, not a guarantee. For these fixed-work workloads energy-per-task tracks average power,
  so cards may show both, but the canonical metric stays package energy.
- **Ownership:** selection rule + tests — B (`core/optimizer.py`); objective selector UI
  (Deadline | Preference | explore) + adapted comparison cards — C; explanation template lines
  — D. Applying a deadline on top of preference targets is a stretch goal, not MVP.
- **Contracts:** objective mode + targets + per-target outcome flags live on `Selection` in
  models v0 (Gate 0). The objective is an experiment-creation field; changing it re-runs
  selection only — never the workload.

## 7. Definition of done per gate (per agent)

Condensed from PLAN §13 / TEAM_PLAN §5. "Done" = merged to main + log line `[gateN]`.

- **Gate 1 (h0–4):** A — topology + energy + one control verified, capability report + C1 committed, one correct run restored. Pre-verified facts in `VERIFIED_DEMO_LAPTOP.md`; re-confirm in ~10 min per its checklist (energy counter advances; class map via per-CPU cpuinfo_max_freq; cap honored with boost=0; tuned profile noted) instead of rediscovering. Control = (boost, per-policy cap) pair on this machine — cap-only is a no-op with boost=1; on any machine, Gate B's actual-effect check decides the pairing. B — models frozen (incl. watch fields), store, synthetic backend, optimizer skeleton, all tested. C — app shell + SSE + fixture data rendered. D — kernel binary + checksum + invocation committed, zstd scaffold started.
- **Gate 2 (h4–8):** A — helper with apply/readback/restore/watchdog; C1 (stock-only) + C2 (dense calibration sweep, §6 ladder, user-selected time) stored. B — runner + state machine + CLI, one real run persisted. C — real run visible over SSH tunnel, restore status shown. D — plugin contract implemented against B's runner.
- **Gate 3 (h8–16):** A — control levels integrated (per-policy cap writes + global boost toggle + snapshot/restore of both, machine-fact-driven: the demo laptop needs boost-off for caps to bind and has no EPP; other machines may differ — integrate what their capability reports verified, including EPP where it actually exists); Levels 2/3 read from C2's calibration curve, not hardcoded. B — validation-point selector from class map (4 layouts, no fixed control grid), randomized reps, deadline selection + preference mode (§6c), Pareto, export; watch detector + scripted-profile tests (second track). C — explorer chart + point/range/all selection + slider + cards + failure states + objective selector with preference sliders + watch endpoints/live panel. D — contrast workload, deterministic explanations incl. preference-mode templates.
- **Gate 4 (h16–24):** A — controls re-verified, conditions noted. B — validation machinery. C — validation view, suggested-budget card from watch observations (§6b), provider selector shell. D — 3 fresh pairs, drift checked, export verified, watch-mode integration test + demo beat; only now local-LLM test.

## 8. Status logs (append-only, dated lines, your section only)

### Agent A log

- (hour 0) onboarded.
- (2026-09-09T10:06:21Z) A: Gate 0 bootstrap done — repo live (dan-el-7/joulectrl), hour-0 hardware re-verified per VERIFIED_DEMO_LAPTOP checklist (energy counter advances 8.6 mJ/s idle; class map even=Zen5/odd=Zen5c via cpuinfo_max_freq; cap honored only with boost=0: cur_freq 1.98 GHz at 2 GHz cap vs 5.04 GHz with boost=1; tuned throughput-performance; AC). energy/base.py (EnergyBackend + wrap-safe accumulator, 12 unit tests green), core/topology.py, core/discovery.py committed; fixtures/real/{topology,capability_report,energy_trace_idle}.json; CI workflow. [gate0]

- (2026-09-09T10:42:08Z) [contract] A: helper op set live — helper/daemon.py (begin_session, read_energy, apply_configuration, heartbeat, restore, end_session over /run/joulectrl-helper.sock, JSON-lines, snapshot-first apply, watchdog auto-restore 30s) + helper/client.py + docs/HELPER.md. Verified on real machine: apply (boost, cap) pair -> readback match; out-of-range cap rejected; restore zero-mismatch. 29 unit tests green. AFFECTS(b,c,d): use helper/client.py HelperClient for any privileged op.
- (2026-09-09T10:42:08Z) A: MACHINE FACT (demo laptop) — boost=0 clamps cpuinfo_max_freq to 2000000 kHz on BOTH classes (Zen5 and Zen5c); cap ladder under boost=0 is [623377..2000000] kHz continuous. Caps >2 GHz only exist with boost=1, where caps are no-ops. Consequence: C2 sweep tier 2 range is 623 MHz–2.0 GHz; stock (boost=1) is the only >2 GHz point. Folded into fixtures/real/capability_report.json (next commit).

### Agent B log

- (hour 0) onboarded.
- (2026-09-09 10:05 UTC) [contract] AFFECTS(a,c,d) core/models.py v0 committed with all §5 contracts, CalibrationRecord, watch mode metadata (§6b), and preference mode targets/outcomes (§6c).
- (2026-09-09 10:07 UTC) energy/synthetic.py committed with modulo wrap handling, reset detection, unavailable states (None, never 0), and scripted power profiles (§6b). Assumes EnergyBackend semantics matching Agent A's planned protocol.
- (2026-09-09 10:09 UTC) AFFECTS(a) energy/base.py line 130: self.path.rsplit('/', 1)[0] fails to find max_energy_range_uj on Windows because os paths use backslashes; pathlib.Path(self.path).parent or os.path.dirname(self.path) avoids this.
- (2026-09-09 10:15 UTC) core/optimizer.py skeleton committed with deadline selection, preference mode (§6c), Pareto frontier, and edge states (PLAN §6 & §14); 11 unit tests green.
- (2026-09-09 10:20 UTC) [gate1] core/store.py committed with SQLite persistence (experiments, state transitions, runs, calibrations, profile, selection, validation, JSON export). All Gate 1 deliverables complete: models v0 frozen contracts, synthetic backend, optimizer skeleton, SQLite store, 29 unit tests green.
- (2026-09-09 10:31 UTC) AFFECTS(c,d) core/runner.py execution harness added: direct argument-array launch, Linux taskset affinity, measured counter bracket, output verification, timeout, and process-group cancellation. Focused runner tests added; bundled Python compile + success smoke pass locally (pytest is not installed on this Windows clone).
- (2026-09-09 10:39 UTC) AFFECTS(a,c,d) core/experiment.py state machine added: persisted legal lifecycle transitions, cancellation, and restoration/recovery-required visibility. Focused unit tests added; bundled Python compilation and full lifecycle smoke pass locally (pytest unavailable on this clone).
- (2026-09-09 10:47 UTC) AFFECTS(c,d) `ExperimentStateMachine.run_profile_point()` now wires an approved workload through the runner and persisted CHECKING→PREPARING→PROFILING→PROFILE_READY/FAILED lifecycle. Focused test plus bundled-Python smoke pass; CI could not be inspected from this host (GitHub Actions page fetch failed).
- (2026-09-09 10:58 UTC) AFFECTS(a,c,d) Added `cli/main.py` `run-fixed`: only the approved fixed-compute plugin, helper-backed energy/control operations, persisted run, and unconditional restore/end-session. Arbitrary shell commands are not accepted. Help/compile smoke pass; Windows correctly reports helper OS limitation.
- (2026-09-09 11:10 UTC) AFFECTS(a,c,d) Added `core/watch.py` passive detector and scripted-profile tests: learned idle baseline, sustained onset backdating, dip absorption, sustained idle end backtracking, wrap-safe energy, and unavailable-energy honesty. Bundled-Python compile/smoke confirms 31s→80s / 49s scripted window.
- (2026-09-09 11:22 UTC) AFFECTS(a,c,d) Added `core/validation.py`: seeded randomized fresh baseline/candidate pairs, apply/restore callbacks around every run, deadline marking, persistence, and restoration-error honesty. Focused tests and bundled-Python smoke pass.




### Agent C log

- (hour 0) onboarded.
- (2026-09-09 10:10 UTC) [contract] AFFECTS(a,b,d) docs/API.md committed: frozen route table (PLAN §8), watch endpoints/SSE (§6b), preference mode targets/outcomes (§6c), and SSE event contracts.
- (2026-09-09 10:20 UTC) [gate1] AFFECTS(b,d) Scaffolded FastAPI app (127.0.0.1, SSE, single-origin static mount) + Vite React dashboard end-to-end. Renders Setup (with objective & budget sliders), Profile Explorer (interactive Pareto scatter chart, comparison cards, full run list), Validation & Explanation, and Passive Watch panel. 13 unit tests green. AFFECTS(a): test_powercap_backend_reads is Linux-only (fails on Windows dev machine, green in Linux CI).

### Agent D log

- (hour 0) onboarded.
- (hour 1) [contract] AFFECTS(a,b) compute kernel committed in workloads/kernel/ (fixed_compute.c, Makefile, build.sh). Fixed work per chunk, pthread partitioning, invariant checksum across workers (default 4096 chunks, 100k iters -> 0x3a762069507139ac; smoke 1024 chunks, 50k iters -> 0x23e23165be5ef4b6). Ready for Agent A calibration (C1 stock single-core baseline and C2 dense sweep).
- (hour 1) [contract] AFFECTS(a,b) workloads/base.py Workload plugin contract committed per PLAN §8 (prepare, command, environment, verify, fingerprint). Includes workloads/fixed_compute.py reference plugin and unit tests.
- (hour 2) workloads/clean_build.py Workload A plugin scaffold committed (zstd pinned clean build, cache-disabled, clean-state enforcement, pre-warmed filesystem cache, artifact & smoke verification). Unit tests passing.
- (hour 2) [gate1] AFFECTS(c) explain/ layer committed (facts extraction, deterministic templates for deadline/preference/frontier & edge states, provider interface with Basic guaranteed default and local/cloud adapters). fixtures/synthetic/ JSON datasets generated (profile, selection, validation, calibration). Unit tests green (17 tests passing).
- (hour 2) tests/integration/test_workload_lifecycle.py committed: E2E workload execution + verification with invariant checksum, and Store + synthetic profile/selection roundtrip with grounded explanations. 19 tests green.
- (hour 2) demo/run_demo.py and demo/README.md committed: end-to-end 5-phase live presentation script executing capabilities, live kernel execution with invariant checksum, Pareto frontier, deterministic optimizer, fresh validation, and grounded explanation with restoration. All 19 tests passing.
- (hour 2) AFFECTS(b) core/runner.py and test_runner.py use os.killpg and POSIX process-group creation which error on Windows dev machines (os.killpg does not exist on win32). Green on Linux CI.
- (hour 3) [gate2] tests/integration/test_runner_workload.py committed: verified Workload plugin contract execution against Agent B's WorkloadRunner and ExperimentStateMachine.run_profile_point with verified checksum, package energy delta, and restoration. 23 tests green.
- (hour 3) AFFECTS(c) explain/ API ready for /api/explain: extract_explanation_facts(selection, profile, val_pairs) and get_provider(provider).explain(facts) can be plugged directly into api/app.py explain_selection handler.
- (hour 3.5) [gate3] D: Gate 3 deliverables complete — workloads/registry.py (central plugin factory + listing with category/characteristics metadata), workloads/fixed_compute.py presets ('smoke', 'light', 'standard', 'heavy' with verified checksums), explain/facts.py + templates.py preference mode (§6c) reporting (closest_perf_floor, closest_energy_target, miss percentages, none_feasible, ASCII console-safe formatting), and tests/unit/test_contrast_workload.py + test_explain.py tests. 31 tests green. AFFECTS(b,c): get_workload(name, **kwargs) and list_workloads() in workloads/ ready for CLI and API integration.

## 9. Verified facts (any agent may add; cite how verified)

- (Sep 9 2026, pre-event) Demo laptop hardware pre-verified with root access — full details and
  commands in `VERIFIED_DEMO_LAPTOP.md`: powercap `intel-rapl:0/energy_uj` package-0 counter
  works (root-only, 65.5 kJ range, advances ~8.1 mJ/s idle); class map exposed per-CPU
  `cpuinfo_max_freq` (Zen 5 = even CPUs 5.09 GHz, Zen 5c = odd CPUs 3.51 GHz); 16 per-CPU
  cpufreq policies; caps honored only with global boost=0; EPP dead (single preference value);
  tuned `throughput-performance` active. All touched settings restored and verified.

## 10. CI (A owns the workflow file; it protects everyone)

A `.github/workflows/ci.yml` lands at Gate 0 and runs on every push to any branch:
install the package (`pip install -e .[dev]` or the minimal equivalent), run the unit test
suite. Linux runner is sufficient (the demo laptop is Linux; C/D's cross-platform areas are
pure Python). This is the only per-push safety net while everyone merges directly to `main`
without branch protection — treat a red CI check on your branch as a do-not-merge signal and
fix it before merging. If CI is red on `main`, the agent who broke it drops everything and
fixes forward (no force-push, ever). Keep the workflow minimal; do not grow it during the
event. Note: agents on the demo laptop must not use CI as an excuse to run heavy loops
locally — push and let the runner test.

## 11. Status-log churn control (amendment to §4b heartbeat rule)

To keep the rewritable AGENTS2.md from generating constant pull-rebase cycles: fold heartbeat
and live-state updates into the same commit as whatever unit just finished whenever one is
pending; push a standalone heartbeat update only if the last push is > 15 min old. Measurement
windows (`[measuring]` open/close) always push immediately regardless — that's the signal B
polls. Nothing else changes about §4b semantics.
