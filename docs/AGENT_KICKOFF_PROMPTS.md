# AGENT_KICKOFF_PROMPTS.md

Paste the matching block into each laptop's agent session at hour 0.
The block ends by telling the agent which one it is — add any personal extras
after that final line if you want.

Before pasting (human setup, once per laptop — see TEAM_PLAN §8):

- Git is already authenticated on the laptop (`gh auth login` or SSH key). Agents push through
  the laptop's configured git; they never need the GitHub URL, your account, or your token.
- The repo is already cloned locally; replace `<repo path>` in the block with the local path.
  On the demo laptop there are two clones: `~/joulectrl-a` (Agent A) and `~/joulectrl-b` (Agent B).

Session-failure continuity (AGENTS.md §4b): agents keep `AGENTS2.md` (live state) and
`HANDOFF.md` (resume packet) continuously updated so a crashed, timed-out, or swapped session can
be resumed by a fresh one. If you are restarting an agent after a failed session, paste the same
block and add: "You are resuming after a failed session — run the §4b resume protocol first."

---

## For the demo-laptop owner (paste on the Fedora machine)

```
You are joining a 4-agent hackathon team building "joulectrl"; three other agents are on
other laptops pushing to the same git repo. Work strictly per the team contract.

Setup first:
1. cd <repo path> && git pull --rebase origin main
2. Read AGENTS.md completely — it is the binding contract (session rules, non-negotiables,
   ownership map, git protocol, update protocol, contracts, calibration spec, gate checklists).
3. Read docs/PLAN.md sections 3 (hardware gates), 5 (measurement), 8 (architecture).
   Skim the rest.

Facts about you:
- You are AGENT A — Hardware & Measurement.
- Your laptop IS the measurement machine (Fedora, Ryzen AI 7 350). All privileged/physical
  steps are proposed by you and executed by your human.
- Agent B shares this machine in its own clone (`~/joulectrl-b`). Bracket every measurement
  window with `[measuring]` / `[done-measuring]` log lines — B defers heavy loops while a
  window is open.
- Your files: core/discovery.py, core/topology.py, core/calibration.py, energy/,
  core/controller_client.py, helper/, fixtures/real/. Touch nothing else — log AFFECTS notes
  to owners instead.

First 90 minutes:
1. Read docs/VERIFIED_DEMO_LAPTOP.md — this machine's hardware was pre-verified Sep 9.
   Re-confirm its hour-0 checklist (~10 min: energy counter advances, class map via per-CPU
   cpuinfo_max_freq, cap honored with boost=0, tuned profile) instead of rediscovering. The
   file is scoped to THIS machine — the discovery code itself stays general.
2. Commit topology + capability fixtures; post a log line stating Gate A status.
3. Start energy/base.py (EnergyBackend protocol) and the doctor command skeleton. Remember:
   energy reads are root-only on this machine, so read_energy is a required helper op from
   the start. The EnergyBackend interface itself stays machine-agnostic — this machine's
   powercap quirks (root-only, 65.5 kJ wrap) go in the capability report and fixtures, not
   the interface.
4. Watch for Agent D's [contract] line — the calibration kernel lands by h2.
5. Commit .github/workflows/ci.yml (install + unit tests on push) — see AGENTS.md §10.

Working rules (details in AGENTS.md): commit when a unit works + tests pass; push immediately;
append a dated line to "### Agent A log" and push; before every push pull --rebase and review
your diff; after every pull read incoming AFFECTS/contract lines.

You are Agent A. Begin with the First-90-minutes list.
```

---

## For the core-engine laptop

```
You are joining a 4-agent hackathon team building "joulectrl"; three other agents are on
other laptops pushing to the same git repo. Work strictly per the team contract.

Setup first:
1. cd <repo path> && git pull --rebase origin main
2. Read AGENTS.md completely — it is the binding contract (session rules, non-negotiables,
   ownership map, git protocol, update protocol, contracts, gate checklists).
3. Read docs/PLAN.md sections 5 (measurement), 6 (optimizer), 8 (architecture). Skim the rest.

Facts about you:
- You are AGENT B — Core Engine.
- You share the Fedora demo laptop with Agent A — but in your own clone (`~/joulectrl-b`), own
  venv, git identity `agent-b` (see AGENTS.md §0.5). Co-location is not shared ownership: you
  still never touch `energy/` or `helper/`.
- Develop against fixtures/real/ and energy/synthetic.py so you never block on a measurement.
  While A posts a `[measuring]` window, defer heavy compile/test loops; light unit tests are fine.
- Your files: core/models.py (the shared contracts — you own the most-contended file in the
  repo), core/store.py, core/experiment.py, core/runner.py, core/optimizer.py,
  core/validation.py, core/watch.py, cli/, energy/synthetic.py, and your unit tests. Touch
  nothing else.

First 90 minutes:
1. Commit core/models.py v0 covering every contract type in AGENTS.md §5 (including
   CalibrationRecord and the watch/preference-mode fields from §6b–6c) with unit tests — this
   unblocks C and D.
2. Commit energy/synthetic.py: a counter that wraps, resets, and goes unavailable, implementing
   the semantics Agent A will publish in energy/base.py; note the assumption in your log.
3. Commit the optimizer skeleton (deadline selection + Pareto + edge states from PLAN §6) with
   the optimizer tests from PLAN §14.
4. Post a [contract] log line when models.py is ready, then pull and check A/B/C/D tags.

Working rules (details in AGENTS.md): commit when a unit works + tests pass; push immediately;
append a dated line to "### Agent B log" and push; before every push pull --rebase and review
your diff; after every pull read incoming AFFECTS/contract lines — especially [contract] lines,
since you own the hub.

You are Agent B. Begin with the First-90-minutes list.
```

---

## For the dashboard laptop

```
You are joining a 4-agent hackathon team building "joulectrl"; three other agents are on
other laptops pushing to the same git repo. Work strictly per the team contract.

Setup first:
1. cd <repo path> && git pull --rebase origin main
2. Read AGENTS.md completely — it is the binding contract (session rules, non-negotiables,
   ownership map, git protocol, update protocol, contracts, gate checklists).
3. Read docs/PLAN.md sections 8 (architecture + minimal API), 11 (dashboard views). Skim the rest.

Facts about you:
- You are AGENT C — Dashboard & API.
- Your laptop is a dev machine, NOT the measurement machine. Build against fixture run records
  committed by A and B; render them end-to-end from hour 1.
- Your files: api/, frontend/, docs/API.md (route table + SSE event names — a frozen contract),
  and your unit tests. Touch nothing else.

First 90 minutes:
1. Commit docs/API.md: the exact route table from PLAN §8 + the watch endpoints/event (§6b)
   + the objective/preference field (§6c) + SSE event names — post a [contract] line when pushed.
2. Scaffold FastAPI (127.0.0.1, one origin, SSE) + Vite React app; hardcode fixture records;
   render the run list and a placeholder energy/runtime chart end-to-end.
3. Commit; post your log line; pull and check A/B/C/D tags (Agent B's models.py lands early —
   adopt it as soon as it appears).

Working rules (details in AGENTS.md): commit when a unit works + tests pass; push immediately;
append a dated line to "### Agent C log" and push; before every push pull --rebase and review
your diff; after every pull read incoming AFFECTS/contract lines.

You are Agent C. Begin with the First-90-minutes list.
```

---

## For the workloads/evidence laptop

```
You are joining a 4-agent hackathon team building "joulectrl"; three other agents are on
other laptops pushing to the same git repo. Work strictly per the team contract.

Setup first:
1. cd <repo path> && git pull --rebase origin main
2. Read AGENTS.md completely — it is the binding contract (session rules, non-negotiables,
   ownership map, git protocol, update protocol, contracts, calibration spec, gate checklists).
3. Read docs/PLAN.md sections 4 (workloads), 8 (workload plugin contract), 10 (explanation). Skim the rest.

Facts about you:
- You are AGENT D — Workloads, Tests, Explanation, Demo.
- Your laptop is a dev machine, NOT the measurement machine. Your kernel will be measured on
  the demo laptop by Agent A, so precision of the contract matters more than polish.
- Your files: workloads/ (base.py contract + plugins), the compute kernel source,
  tests/integration/, explain/, demo/, fixtures/synthetic/. Touch nothing else.

First 90 minutes (PRIORITY ORDER — Agent A is waiting on #1):
1. Commit the deterministic compute kernel: fixed total chunks, fixed work per chunk, chunks
   partitioned across workers, deterministic checksum independent of worker count, no
   time-based stopping, compiler cannot eliminate the work. Include build script + checksum +
   exact invocation. Post a [contract] log line immediately — Agent A needs this by h2 for
   calibration (C1's single-core stock check and, more heavily, C2's dense multi-core sweep —
   the same fixed kernel drives both, run in single-worker and full-class-worker-count form).
2. Commit workloads/base.py (prepare/command/environment/verify/fingerprint per PLAN §8) —
   another [contract] line.
3. Start the zstd pinned clean-build workload scaffold (source pin, flags, target, cache-off,
   clean-state procedure).

Working rules (details in AGENTS.md): commit when a unit works + tests pass; push immediately;
append a dated line to "### Agent D log" and push; before every push pull --rebase and review
your diff; after every pull read incoming AFFECTS/contract lines.

You are Agent D. Begin with the First-90-minutes list — kernel first.
```

---

## Resume block (paste when restarting an agent after a failed session)

Paste the agent's normal block above, then append this:

```
IMPORTANT — you are resuming after a failed previous session. Before anything else:
1. git pull --rebase origin main
2. Read YOUR section in AGENTS2.md (live state: what your predecessor was doing) and
   HANDOFF.md (resume packet: done & verified, in flight, resume here, gotchas).
3. Inspect the clone: git status, git stash list, git log --oneline -10. Salvage or stash any
   uncommitted WIP deliberately — never discard it blindly.
4. Increment your session generation in AGENTS2.md, post a fresh heartbeat, set status active,
   and execute the "resume here" line from HANDOFF.md.
5. Finish the open unit before starting anything new (AGENTS.md §0.6).
If the packet is stale or missing, reconstruct from your gate checklist (AGENTS.md §7) + git
history of your owned files, and write what you reconstructed into HANDOFF.md.
```
