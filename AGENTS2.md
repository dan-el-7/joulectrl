# AGENTS2.md — live state board (rewritable, high-frequency)

Companion to `AGENTS.md` (process contract) and `HANDOFF.md` (resume packets).
**This file answers one question at all times: "what is every agent doing right now, and what
was each agent's last known state?"** It is the first file a resumed/replacement session reads
after a model failure, crash, timeout, or session swap.

Unlike `AGENTS.md` §8 (append-only history), **this file is REWRITABLE**: each agent replaces
its own section's content on every update instead of appending. History lives in AGENTS.md §8;
live state lives here.

## Rules

1. Each agent owns exactly one section below and may freely rewrite **its own** section — never
   another agent's. A rescuing agent (see below) marks its edits `[rescued-by <letter>]`.
2. Same git discipline as AGENTS.md §4: `git pull --rebase origin main` before editing, review
   your diff, push **immediately** after every update. Never leave this file dirty locally.
3. Update triggers — every one pushes immediately:
   - session start (post your heartbeat + session generation before doing anything else);
   - starting and finishing any unit of work;
   - every commit / push / merge to main;
   - `[blocked]` / `[unblocked]` transitions;
   - entering / leaving a `[measuring]` window (A especially — B polls this);
   - any contract-relevant discovery (also gets a `[contract]` line in AGENTS.md §8);
   - heartbeat refresh at least every **15 minutes** while working;
   - a final update when ending a session (status: `off`).
4. **Session generation:** each new session for a letter increments its generation
   (`A#3` = Agent A's third session). A generation jump without a matching HANDOFF.md update
   means the predecessor died mid-work — run the resume protocol (§4b in AGENTS.md).
5. **Staleness = failure signal:** if your heartbeat is > 20 min stale, your human (and
   teammates) should treat the session as possibly dead. Humans confirm death; agents never
   assume it just from staleness (long measurements happen — A brackets those with
   `[measuring]` + an expected end time, so a stale heartbeat *during* a bracketed window is
   normal).
6. Keep entries short — this is a dashboard, not a diary. One line per field where possible.

## Rescue rule (when a session is confirmed dead)

Preferred: paste a fresh session on the same laptop with the same letter and run the §4b resume
protocol. If no replacement is available and the dead agent is blocking the critical path, the
human may direct the nearest upstream/downstream agent to rescue: the rescuer updates the dead
agent's HANDOFF.md section (marked `[rescued-by <letter>]`), does the minimum to unblock the
spine, and appends the work to its **own** AGENTS.md §8 log with `AFFECTS(<dead-letter>)`.
Ownership boundaries still apply — a rescue is an exception granted by a human, not a land grab.

---

## Agent A — live state

- heartbeat: 2026-09-09T10:07:39Z
- session: `A#1` · status: `active`
- branch: `main`
- current unit: reading B's models v0; next unit: helper/ skeleton (docs/HELPER.md + op set)
- next action: pull, adapt energy/base.py + discovery output to core/models.py contracts
- notes for others: fixtures/real/*.json are committed and current — build against them. D: kernel [contract] line expected by h2.


## Agent B — live state

- heartbeat: 2026-09-09T10:41:00Z
- session: B#2 · status: off
- branch: main
- current unit: Gate 2 runner and persisted experiment state machine complete
- next action: inspect CI, then integrate validation orchestration or CLI as the Gate 2 priority requires
- notes for others: runner is ready for D workload plugins and C's run events; its Windows path uses process.terminate(), not os.killpg. pytest is unavailable on this clone, but compile and direct smoke passed.






## Agent C — live state

- heartbeat: `2026-09-09T10:20:00Z`
- session: `C#1` · status: `active`
- branch: `on main`
- current unit: `Gate 1 scaffolded: FastAPI (127.0.0.1, SSE) + Vite React app + 13 unit tests green`
- next action: `Awaiting Agent B runner state machine & live SSE events integration for Gate 2`
- notes for others: `Dashboard renders full 12-config Pareto curve, comparison cards, and watch panel; ready for live runner events`

## Agent D — live state

- heartbeat: `2026-09-09T10:40:00Z`
- session: `D#1` · status: `active`
- branch: `d/demo-scaffold`
- current unit: `committed demo/run_demo.py and demo/README.md; Gate 1 complete, Gate 2 ready`
- next action: `wire Workload plugins into Agent B runner upon Gate 2 merge`
- notes for others: `All deliverables up to Gate 2 complete: kernel, workloads, synthetic fixtures, explain layer, integration tests, and live demo script.`
