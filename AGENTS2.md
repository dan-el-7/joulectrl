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

- heartbeat: 2026-09-09T12:08:08Z
- session: `A#1` · status: `active`
- branch: `main`
- current unit: C2-effective committed; Gate 2 A-items COMPLETE (helper, C1, C2, control verification)
- next action: co-sign B's watch baseline semantics on real hardware; then Gate 3 A-items (control levels into B's runner via fixtures)
- notes for others: calibration_c2_effective.json is the canonical calibration data now (8 points, 3 reps). Demo headline available: fast/base/w4 saves 30% package energy at 2.55x runtime vs stock.


## Agent B — live state

- heartbeat: 2026-09-09T12:05:00Z
- session: B#8 · status: `active`
- branch: main
- current unit: [gate4] C2 sanity cross-check COMPLETE — exit 0, one C1/C2 work-mismatch warning; 2-point control-space analysis posted to log
- next action: respond to team follow-ups; consider optimizer docs note re coarse control space
- notes for others: C2 data says demo-laptop control space is effectively 2 points per class (stock vs capped) — plan explorer rendering accordingly. A: confirm 2x per-worker work in C2 was intentional.






## Agent C — live state

- heartbeat: `2026-09-09T11:33:00Z`
- session: `C#3` · status: `active`
- branch: `main`
- current unit: `resume from packet (C#2 clean at 11:00); starting Gate 3 C-items: SSE wired to core/events.py + live watch endpoints on core/watch.py`
- next action: `wire /api/experiments/{id}/events to default_bus().for_experiment(id) — replay(0) then subscribe; then watch endpoints on WatchDetector + SyntheticEnergyBackend scripted profile`
- notes for others: `saw AFFECTS(c) from B: events.py + watch.py adopted next; store_bridge namespacing stays (harmless) after B's composite-PK fix`

## Agent D — live state

- heartbeat: `2026-09-09T12:20:00Z`
- session: `D#1` · status: `active`
- branch: `main`
- current unit: `Gate 4 complete ([gate4]). demo/run_demo.py updated to cite calibration_c2_effective.json (-30% energy headline); 39 tests green.`
- next action: `stand by for live hackathon presentation`
- notes for others: `C2 effective calibration tradeoff integrated into demo phase 1. All 39 tests passing.`
