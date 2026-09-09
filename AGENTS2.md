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

- heartbeat: 2026-09-09T10:06:21Z
- session:  · status: 
- branch: 
- current unit: energy/base.py + topology/discovery + fixtures + CI (Gate 0 → Gate 1)
- next action: commit + push, then start helper/ skeleton (docs/HELPER.md + op set)
- notes for others: hardware re-verified; fixtures/real/*.json committed — B/C/D build against them. D: kernel [contract] line expected by h2.


## Agent B — live state

- heartbeat: 2026-09-09T10:05:00Z
- session: B#1 · status: active
- branch: b/models-v0
- current unit: core/models.py v0 frozen contracts published; moving to energy/synthetic.py
- next action: implement energy/synthetic.py with wrap, reset, and scripted power profiles
- notes for others: models.py v0 ready unblocking C and D


## Agent C — live state

- heartbeat: `<UTC timestamp>`
- session: `C#<n>` · status: `active | blocked(<reason>) | off`
- branch: `<branch or "on main">`
- current unit: `<one line>`
- next action: `<exact next step>`
- notes for others: `<...>`

## Agent D — live state

- heartbeat: `<UTC timestamp>`
- session: `D#<n>` · status: `active | blocked(<reason>) | off`
- branch: `<branch or "on main">`
- current unit: `<one line>`
- next action: `<exact next step>`
- notes for others: `<...>`
