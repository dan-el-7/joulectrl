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

- heartbeat: 2026-09-09T17:55:00Z
- session: `Antigravity` (Agent A successor) · status: `active (idle)`
- branch: `main`
- current unit: dynamic time-budget fitting loop & multiresolution bisection candidate sampling (extremes -> midpoints -> quartiles -> octiles)
- next action: standby for user instructions / review
- notes for others: demo is Sep 10 — pre-demo `core/reverify_controls.py` + fresh controls_reverify.json still owed; tagged release pending. History rewrite note: clones may need git pull --rebase.


## Agent B — live state

- heartbeat: 2026-09-09T14:05:00Z
- session: B#8 · status: `active (responding to wake triggers: all-cores fixture validated, C question answered)`
- branch: main
- current unit: none — all B gate-items delivered
- next action: SLEEP. Wake triggers (A → human → B): AFFECTS(b)/[contract] lines, demo-laptop support, review/rescue request. Otherwise stay parked.
- notes for others: A — you're the head: if anything above triggers, prompt the human to wake B. Everything B-owned is green (153 tests).






## Agent C — live state

- heartbeat: `2026-09-09T14:15:00Z`
- session: `C#4` · status: `active (idle — all user asks + integration items complete)`
- branch: `main`
- current unit: none — all-cores calibration integrated (04672ee) and browser-verified: pickers (fast/efficient/all classes, single/multicore scope) filter 24/8/8/16 points, all16 dominated by all8 visible in data, no clipping, no hardcoded spec strings
- next action: autonomous poll mode (cron job every 10 min, change-detect on remote HEAD); respond to AFFECTS(c)/[contract] lines or human prompts

## Agent D — live state

- heartbeat: `2026-09-09T13:38:00Z`
- session: `D#1` · status: `shutdown (clean)`
- branch: `main`
- current unit: `Clean shutdown per A conclusion plan (a2cdcd1). All gates done, 39/39 tests green, board quiet.`
- next action: `none — session ended cleanly`
- notes for others: `D is done. SESSION_START_D.md has full resume packet. 39 tests always green. Demo-ready.`
