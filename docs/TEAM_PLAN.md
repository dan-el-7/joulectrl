# joulectrl — Team Coordination Plan (4 agents, 36 h)

**Read together with `finalplan.md`.** That file is the product/technical spec; this file covers
only how four humans + four AI agents split the build and stay out of each other's way.

Companion files in this folder:

- `AGENTS.md` — the contract the agents follow. Copy it into the repo root at hour 0.
- `AGENT_KICKOFF_PROMPTS.md` — one paste-block per laptop; each ends by telling the agent which one it is.

---

## 1. The split

| Agent | Name | Laptop | Owns (hard boundary) | Must not touch |
|---|---|---|---|---|
| **A** | Hardware & Measurement | **the Fedora demo laptop** | topology discovery, core-class calibration, energy backend, `doctor`, privileged helper, apply/restore, real-machine fixtures | optimizer, store, UI, workloads |
| **B** | Core Engine | **the Fedora demo laptop** (shared with A — separate clone) | `core/models.py` (shared contracts), SQLite store, experiment state machine, runner, optimizer, validation, CLI, watch-mode detector | energy/helper internals, UI, workloads |
| **C** | Dashboard & API | any dev laptop | FastAPI app + SSE, React dashboard, charts, states, API route contract | core logic, hardware code |
| **D** | Workloads & Evidence | any dev laptop | compute kernel (calibration + Workload B), clean-build workload, workload plugin contract, integration tests, explanation layer, export, demo assets | hardware, optimizer, UI |

The dependency spine:
**D's kernel → A's calibration → verified core-class map → C's curve explorer → B's user-selected workload validation → everyone's demo.**

Why this splits cleanly for agents: **no agent is blocked on hardware.** A is gated on it; B
*shares the demo laptop* but still develops against the synthetic backend, so it never waits on
a measurement (bonus: it can smoke-test runner code against real fixtures instantly). C and D
develop on their own laptops against frozen interfaces + committed fixtures. A remains the only
serialized resource, and A's outputs (fixtures, capability report, calibration records) are
committed as JSON so the others build against *real* shapes.

### Same-laptop pairing (A + B on the demo machine)

- **Two isolated clones**: `~/joulectrl-a` (Agent A) and `~/joulectrl-b` (Agent B), each with its
  own venv. The agents never touch each other's working tree; the shared remote stays the only
  coordination channel — exactly as with C and D.
- **Distinct git identities** on that machine: `user.name` = `agent-a` / `agent-b`, so diffs and
  log lines stay attributable.
- **Measurement windows win**: A brackets every calibration/sweep/validation window with
  `[measuring]` / `[done-measuring]` log lines (the helper's exclusive lease is the machine-truth
  signal). While a window is open, B defers heavy compile/test loops on this machine — light
  editing and quick unit tests are fine.
- **Boundaries unchanged**: co-location is not shared ownership. B still never touches `energy/`
  or `helper/`; A still never touches B's files. The upside: Gate 1/2 handshakes (models ↔ energy
  semantics, runner ↔ real runs) happen same-room, same-machine.

---

## 2. The three coordination rules that make it work

1. **Contracts before code (hour ≤ 3).** B commits `core/models.py`; C commits the API route
   table; A commits the helper op list + `energy/base.py` semantics; D commits the workload plugin
   signature. After that, interface changes go *only* through the contract-change protocol in
   AGENTS.md (owner edits + `[contract]` log line + immediate push).
2. **Push when it works.** A "unit" = works + its own unit tests pass. Commit it, push it, append
   one dated line to your AGENTS.md log section. Small and often; no big-bang pushes.
3. **Diffs before and after.** Before every push: `git pull --rebase`, then review
   `git diff origin/main..HEAD`. After every pull: read incoming AGENTS.md diffs for `AFFECTS(...)`
   tags. At every gate, each **human** reviews one other agent's branch diff against this plan —
   that is the "don't lose something in the process" check.
4. **Live state + handoff (model-failure insurance).** Every agent keeps two extra root files
   current at all times — `AGENTS2.md` (rewritable per-agent live state: heartbeat, current
   branch, WIP, exact next action) and `HANDOFF.md` (per-agent resume packet written for a
   brand-new model: done/verified, in flight, resume-here line). When a session dies, times out,
   or gets swapped, its successor runs the resume protocol (AGENTS.md §4b) and picks up from the
   handoff instead of losing the hour. Full spec: AGENTS.md §4b.

---

## 3. Git protocol (short version; authoritative rules in AGENTS.md)

- One remote. `main` is always demoable. **No force-push, ever.** Linear history via
  `git pull --rebase`.
- Code: branch `<letter>/<topic>` → push as units land → merge to `main` when the unit is done,
  its tests pass, and only your owned files changed.
- `AGENTS.md` and `docs/`: push straight to `main`, **immediately** whenever you finish something
  (log line, verified fact, contract note). Append inside your own section only.
- Contracts: changed only by their owner, with a `[contract]` log line, pushed immediately.
  Everyone else rebases and adapts at their next pull.
- Never commit: model weights, `.venv`, run data, secrets, build outputs.
  Real-machine **JSON fixtures** (topology, capability report, calibration records, one short
  energy trace) are explicitly wanted in `fixtures/real/` — small, auditable, and they let
  B/C/D develop against the actual machine.
- Hour-0 guard against cross-laptop noise: commit a `.gitattributes` (`* text=auto eol=lf`) and a
  proper `.gitignore` on day one — Windows dev laptops + Fedora demo laptop will otherwise
  fill every diff with CRLF churn.

---

## 4. Calibration workstream — the CPU-set benchmarks (new, per team decision)

Goal: hard data on how the CPU's core sets scale performance and power, stored as first-class
metrics and used to steer workload validation. This is *not* a side experiment — it produces
the verified "4 faster cores" mask that the whole config grid depends on.

- **Discover sets, don't assume them.** Topology reads (`lscpu -e`, per-CPU
  `cpuinfo_max_freq`, amd_pstate info) give candidate core classes (the Ryzen AI 7 350 should
  expose two classes across its 8 cores / 16 threads). CPU numbering alone is not evidence —
  the C1 benchmark *empirically confirms* which set is faster. **Pre-verified on the demo
  laptop (Sep 9):** classes ARE exposed — per-CPU `cpuinfo_max_freq` is 5.09 GHz on even
  logical CPUs (Zen 5, physical cores 0/2/4/6) and 3.51 GHz on odd (Zen 5c, cores 1/3/5/7).
  The layout-A/D masks are therefore known up front; C1 still runs to validate empirically
  and produce the perf/watt curve.
- **Pre-verified control reality (demo laptop):** 16 per-CPU cpufreq policies (caps written
  per policy); caps are honored ONLY with the global `boost` knob off — each swept level is a
  (boost, cap) pair there; EPP is dead (single available preference). Package energy reads are
  root-only, so the helper's `read_energy` is on the critical path from hour 0. These are
  machine facts for THIS laptop — on other hardware, Gate B's actual-effect testing decides
  which controls bind and whether EPP is a usable fallback. Details:
  `VERIFIED_DEMO_LAPTOP.md`.
- **C1 — one core per set, stock only (class validation + the scaling-efficiency baseline).**
  Run D's deterministic kernel pinned to one core from each set (≥5 reps, quiet mode), stock
  config only. Record per set: median runtime, package energy, average watts, work/sec. This
  empirically validates the class map and gives the single-core number that C2's scaling
  efficiency divides by. **C1 is deliberately kept cheap and single-point — it is not where the
  perf/watt curve comes from.**
  - If all CPUs share one cpufreq policy, caps are simply global — that is fine: measure each
    class's single core under the same cap. (On the pre-verified demo laptop this does NOT
    apply: 16 per-CPU policies, so write the cap to every policy and read each back; and the
    cap only takes effect with global boost=0 — see `VERIFIED_DEMO_LAPTOP.md`.)
- **C2 — all four cores of a set, densely swept (the actual perf/watt curve, user-selected time).** Same kernel, at each class's natural full-physical-core layout (4 workers, one
  sibling each — Layout A's shape / Layout D's shape). First row is stock, giving **scaling
  efficiency** = (4-core throughput) / (4 × C1's single-core throughput). Then sweep a ladder
  of control points instead of the old fixed 3 grid levels — three points was never enough for
  a real curve:
  1. Discrete frequency list exposed → test every listed step (small, bounded — this is
     literally "test them all").
  2. Continuous cap range, no discrete list (this machine's case, amd-pstate-epp) → N evenly
     spaced cap values between the class's verified min and max, boost held at whatever Gate B
     found necessary. N is computed from a time-budget formula (PLAN §4, Calibration Sweep),
     not hardcoded; finite density follows the user-selected time budget, while Unlimited/Exhaustive covers every distinct measurable control point.
  3. Caps ineffective → every supported EPP tier (typically 2–4), labeled as a tier, not GHz.
  4. No effective control at all → skip the curve for that class; record it in the capability
     report; that class's grid rows fall back to affinity + worker-count only.
  Only drop to the next tier when Gate B–style verification shows the tier above genuinely
  doesn't work — never pre-emptively degrade. If the time budget allows far more than ~20
  points, spend the slack on a second rep per point rather than a bigger N; one rep is fine for
  a shape-finding pass if the budget is tight.
- **Grid removal (team decision, folded into PLAN §4):** Layout D remains as an execution layout,
  but there is no fixed 12-configuration grid. Preserve the full calibration curve and expose it in the
  explorer. The user selects measured control points for expensive workload validation. Convenience
  markers (stock / minimum-energy / maximum-performance / best-performance-W / knee / Pareto) are
  derived from measurements and are suggestions only.

- **Stored as** `CalibrationRecord` rows (a frozen contract in `core/models.py`) + exportable
  JSON, tagged `phase="calibration"` so they never mix into the workload Pareto chart. No schema
  change needed — the dense sweep is just many more rows of the same shape. Consumed by: the
  layout-A and layout-D masks and their derived control levels, the dashboard hardware card,
  the explanation facts, and as a sanity cross-check on sweep numbers. The same stored curve
  also seeds control-level picks for any workload the user profiles later, not just the two
  built-in ones — no need to re-sweep per workload, only when machine-level state changes
  (same triggers as Profile Validity, PLAN §12).
- Runs on the demo laptop after Gate A (energy counter verified) and before user-selected workload
  sweep. Stock C1 lands at Gate 1; C2's dense sweep lands at Gate 2 once controls are verified.
  **The kernel comes from D by hour ~2 — that is D's first deliverable**, and the same binary
  later serves as Workload B.

---

## 4.5 Watch mode — how the tool learns what your task costs (estimate tier)

Why it exists: the product needs a runtime budget to optimize against, and the honest source of
that number is measurement — not the user with a stopwatch. For the bundled/plugin workloads the
harness measures it (profiling runs produce the runtimes). For a task the user runs *outside*
the harness — their own loop/script — watch mode is how the tool itself learns it: watch the
package-power trace, detect **idle → activity → idle**, record the task's real duration with an
internal monotonic clock (plus estimated task-window energy), and turn those observations into a
**suggested budget** that pre-fills the Setup slider. It is the front door of the product flow:

```text
watch (observe the user's own task) → suggested budget → harness profile → selection → validation
```

Full spec: AGENTS.md §6b. The mechanism:

- **Idle baseline** learned at watch start (~30–60 s of genuine idle: median + spread), recalibrated
  whenever sustained idle is re-detected; baseline parameters stored in the record for audit.
- **Onset:** power leaves the idle band and *stays out* for ≥ N seconds (default 2–5 s,
  configurable) → confirmed start, then **backdated** to the first above-band sample. The
  sustained requirement kills false starts from background blips.
- **End — the "don't get fooled by dips" rule:** a mid-task power dip is *not* the end. Declare
  rest only after the trace has held inside the idle band for a sustained grace period
  (default ~10 s, configurable); then set activity end = the **last above-band sample**
  (backtracked). Trailing settle time never counts toward runtime, and a short dip inside the
  grace window is absorbed into the task window automatically.
- **Long idle** (inside the band for > ~60 s) closes the window; the next spike opens a new
  segment, listed separately. No auto-merging of segments.
- **Lightweight watcher:** poll at 0.5–1 Hz — the tool must not perturb the machine it watches.
  Detection uncertainty ≈ one poll interval; say so on the label.
- **Honesty guards:** results are **estimates** ("measured via idle-return detection"), carry
  `mode="watch"`, and are excluded from the harness Pareto/selection evidence by default —
  they inform the budget and provide context; the selection itself still runs on harness-measured
  runtimes of the profiled workload. Watch mode never applies controls (read-only; `read_energy`
  only, no helper lease) and keeps the "missing energy is never zero" rule.
- **Schedule:** contracts land at Gate 0 (cheap now — `RunRecord.mode` + detection fields in
  models v0, watch endpoints/event in C's route table). Implementation is a **first-class
  Gate 3–4 workstream**: B — detector + scripted-profile tests (second track inside Gate 3,
  after the grid builder); C — watch endpoints + live panel (Gate 3), suggested-budget card
  that pre-fills Setup (Gate 4); D — integration test + demo beat (Gate 4). Leftovers stay in
  polish. Timing-only fallback (utilization-based onset, runtime-only) is a stretch goal.

---

## 4.6 Preference mode — the "70% power / 90% perf" slider (third objective)

A user-selectable objective alongside Deadline mode (default, primary) and the descriptive
frontier view. The user expresses a tradeoff as two percentages relative to the measured
baseline: **energy target** (e.g. ≤70% of baseline energy) and **performance floor** (e.g. ≥90%
of baseline speed = runtime ≤~111% of baseline). Full spec: AGENTS.md §6c.

- **Deterministic rule over measured configs only:** eligible = usable configurations meeting
  *both* targets (feasibility on guarded runtimes, same margin machinery as Deadline mode);
  pick minimum median energy, tie-break on runtime then config id. The baseline itself is a
  candidate.
- **When nothing meets both:** never silently relax a target — report the closest honest
  outcomes explicitly (best meeting the perf floor + its energy miss; best meeting the energy
  target + its runtime miss) and mark the outcome state. Edge states mirror Deadline mode.
- **Labeling:** for these fixed-work workloads, energy-per-task tracks average power, so cards
  may show both — but the canonical metric stays package energy, and the claim stays
  "lowest-energy measured configuration meeting your preference rule". 70/90 is a target, not a
  guarantee.
- **Ownership:** selection rule + tests — B; objective selector (Deadline | Preference) +
  adapted comparison cards — C; explanation template lines + live-slider demo beat — D.
- **Contracts/schedule:** objective mode + targets + per-target outcome flags go into
  `Selection` in models v0 (Gate 0); implementation in Gate 3 (B after deadline selection,
  C's Setup selector); changing the objective re-runs selection only — never the workload.
  Applying a deadline on top of preference targets is a stretch goal.

---

## 5. Gate schedule (36 h)

Same gates as finalplan §13, with per-agent exits. "Merged" = on `main`.

### Gate 0 — Bootstrap (h 0–1)
- All: repo live, `AGENTS.md` at root, `finalplan.md` → `docs/PLAN.md`,
  `VERIFIED_DEMO_LAPTOP.md` → `docs/` (pre-verified hardware facts for the demo laptop),
  `.gitattributes` + `.gitignore`, everyone pastes their kickoff prompt, everyone posts an
  "onboarded" log line.
- B: `core/models.py` v0 pushed (including the watch-mode and preference-mode fields,
  §4.5–4.6). C: route table + empty app shell. A: discovery reads started on the demo laptop
  (re-confirm per the pre-verified checklist, ~10 min, then capability report JSON) **and the
  CI workflow committed**. D: kernel source + build instructions committed.
- **Handshake H0:** all four agents read the four contract diffs; objections now or never.

### Gate 1 — Physical proof (h 0–4)
**Gate: real joules + real seconds from one correct run, then verified restore.**
- A: topology verified, one energy backend reading (verified, not just listed), one effective
  control verified, capability report committed, **C1 single-core stock-only calibration
  numbers committed as fixtures**.
- D: kernel binary + checksum + exact invocation committed early (by h2); zstd pinned clean-build
  scaffold started.
- B: models frozen, SQLite store, synthetic energy backend (wraps + resets) with tests, optimizer
  skeleton with tests.
- C: app shell + SSE + dashboard rendering fixture data end-to-end.
- Humans: **contingency decision here** if energy is unreadable (finalplan §3 options).

### Gate 2 — First end-to-end (h 4–8)
**Gate: UI → workload → measurement → stored → UI, on the real machine.**
- A: helper + apply/readback/restore + watchdog; **C1 (stock-only) + C2 (dense calibration
  sweep, user-selected-time, ladder-based — §4) stored**.
- B: runner + experiment state machine + CLI; one real run persisted.
- C: dashboard shows the real run over SSH tunnel from their laptop; restore status visible.
- D: workload plugin implements the contract against B's runner; correctness verify works.

### Gate 3 — Core loop complete (h 8–16)
**Gate: full calibration curve → user-selected workload validation → reproducible selection.**
- A: cap/EPP control levels integrated (Levels 2/3 read from C2's calibration curve, not
  hardcoded); conflicting-policy detection.
- B: grid builder from the verified class map (4 layouts, incl. efficient-cores-only D),
  randomized reps, deadline selection,
  preference-mode selection (§4.6), Pareto, export; watch-mode detector + scripted-profile
  tests (second track, §4.5).
- C: profile explorer chart, deadline slider, comparison cards, failure states; objective
  selector with preference sliders (§4.6); watch endpoints + live watch panel (§4.5).
- D: contrast workload through the same harness; deterministic explanation templates live.

### Gate 4 — Evidence (h 16–24)
**Gate: honest evidence exists, savings or not.**
- B: validation-pair machinery. D: 3 fresh validation pairs recorded; drift investigated;
  export checked; watch-mode integration test + demo beat.
- A: controls re-verified; AC/thermal conditions noted in fixtures.
- C: validation view + suggested-budget card from watch observations (§4.5) + provider selector
  UI shell.
- **Only now:** D tests the local LLM explanation (after measurements; quiet-mode rules apply).

### h 24–30 — Polish
Watch-mode leftovers, explanations, replay mode, recovery tests, screenshots/video, pitch deck
(D leads).

### h 30–36 — Freeze
No new features, no new tuning dimensions, no new backends. One live pair rehearsed, restore
recovery checked, raw data saved, offline assets (compiler, sources, model weights) ready.

---

## 6. What the humans do

- **Supervise one agent each.** Unblock, approve scope additions, keep the agent on its gate checklist. The demo laptop runs two agents (A and B) — one human can supervise both, or two humans share the machine; privileged steps are still human-executed.
- **Execute privileged/physical steps** on the demo laptop: sudo, AC power, service checks, lid/thermal common sense. Agents propose; humans execute privileged ops.
- **Diff-review rotation at each gate**: each human reviews one *other* agent's branch diff against this plan.
- **Own the go/no-go calls:** hour-4 energy contingency, any contract change, any scope addition.
- **Guard quiet mode:** no LLM demos, no big downloads, no browser bloat on the demo laptop during measurements; view the dashboard from another laptop over SSH.

---

## 7. Risks → answers already built into the plan

| Risk | Answer |
|---|---|
| No readable package energy on the demo laptop | B/C/D are hardware-independent (synthetic backend + fixtures); replay vs second-machine contingency decided at h4 |
| Agents collide on shared files | hard ownership map + frozen contracts + append-only log sections |
| Someone loses work in a merge | push-often, rebase discipline, diff review before every push, human diff rotation at gates |
| Agent gold-plates | scope = your gate checklist; anything else needs a human go |
| A and B share one machine | two isolated clones + own venvs + distinct git identities; B defers heavy loops during `[measuring]` windows |
| Measurements polluted by dev activity | quiet mode + dashboard over SSH + fixed calibration/sweep order |
| CRLF/line-ending churn across OSes | `.gitattributes` with `eol=lf` committed at Gate 0 |
| Background blips fake a watch session's start/end | sustained above-band onset requirement + sustained-rest grace period + segment separation; user can label/confirm observed runs |
| An agent session dies mid-unit (crash, timeout, context exhaustion, model swap) | `AGENTS2.md` live-state heartbeat (staleness > 20 min = failure signal, humans confirm) + `HANDOFF.md` resume packet + the §4b resume protocol; replacement session on the same laptop resumes from the packet; human-directed rescue only if the spine is blocked |

---

## 8. Starting checklist (~20 min)

1. **You (owner):** create the GitHub repo under your account — the demo laptop does this
   step (it already has `gh` authenticated as the owner account; humans, do NOT hand your
   token to other laptops, invite collaborators instead per step 2). On it: `git init`;
   commit `finalplan.md` as `docs/PLAN.md` and `VERIFIED_DEMO_LAPTOP.md` into `docs/`; copy
   this folder's `AGENTS.md`, `AGENTS2.md`, and `HANDOFF.md` to the repo root; add the
   `LICENSE` (MIT, team copyright), `.gitattributes` + `.gitignore`; push. Repo name
   spelling: **`joulectrl`** (j-o-u-l-e-c-t-r-l) — the conflict check in the plan was done
   under that exact name.
2. **You:** Settings → Collaborators → invite the other three humans with **write** access
   (free on public and private repos on GitHub Free). Everyone pushes under their own account —
   never share your token. Skip branch-protection rules for the hackathon: the git protocol in
   AGENTS.md is the discipline, and the one hard rule (nobody force-pushes) is already there.
   You administer the repo; you are *not* a merge bottleneck — per protocol everyone merges
   their own units directly.
3. **Each laptop, once, by the human:** authenticate git (`gh auth login`, or add an SSH key).
   Agents push through whatever the laptop's git is configured with — they never need the
   GitHub URL, your account, or your token. Then clone (two clones on the demo laptop:
   `~/joulectrl-a` and `~/joulectrl-b`), open the agent session, paste the matching block from
   `AGENT_KICKOFF_PROMPTS.md` (fill in `<repo path>`; append any personal extras after the
   final line).
4. Confirm all four agents have pulled and posted an "onboarded" line in their log section.

---

## 9. Agent identity one-liners (quick copy)

- **A:** You are Agent A — Hardware & Measurement, running on the Fedora demo laptop.
- **B:** You are Agent B — Core Engine (models, store, runner, optimizer, validation, CLI).
- **C:** You are Agent C — Dashboard & API.
- **D:** You are Agent D — Workloads, Tests, Explanation, Demo.
