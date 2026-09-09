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

- heartbeat: 2026-09-09T10:59:36Z
- session: `A#1` · status: `measuring(until ~11:55Z)`
- branch: `main`
- current unit: C2 dense sweep RUNNING (fast+efficient, stock + 7 cap points each, boost=0, [measuring] window OPEN)
- next action: after sweep: [done-measuring] + commit fixtures/real/calibration_c2.json
- notes for others: [measuring] until ~11:55Z — B defer heavy loops. Pacing directive from dan-el (lead arch): team ahead of schedule, pull next-gate work forward, no idling at gate boundaries.


## Agent B — live state

- heartbeat: 2026-09-09T11:34:00Z
- session: B#7 · status: off
- branch: main
- current unit: synthetic unavailable-counter clock regression fixed
- next action: integrate C's validation/watch endpoints or continue Gate 4 evidence work
- notes for others: CLI uses HelperClient begin/apply/read/restore/end and only FixedComputeWorkload; no arbitrary command path. Windows has no os.getuid/helper socket, so it reports a clear error.






## Agent C — live state

- heartbeat: `2026-09-09T10:40:00Z`
- session: `C#2` · status: `active`
- branch: `main`
- current unit: `resumed (C#2): pulled B store.py + D explain/ + fixtures; verifying Gate 1 build/tests`
- next action: `run npm build + api unit tests, then Gate 2: serve D's synthetic fixtures via store-backed API + explanation rendering in Validation view`
- notes for others: `Gate 1 dashboard committed (9a610b3); adapting Validation view to render explain/ templates next`

## Agent D — live state

- heartbeat: `2026-09-09T11:25:00Z`
- session: `D#1` · status: `active`
- branch: `main`
- current unit: `Gate 4 complete ([gate4]). C1 calibration preset integrated; 38 tests green.`
- next action: `stand by for cross-agent integration and live demonstration execution`
- notes for others: `All deliverables through Gate 4 complete and verified. C1 calibration confirmed 1.45x fast-class speed with invariant checksum 0xc2493c07d6b29c85.`
