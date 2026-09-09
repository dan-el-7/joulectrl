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

- heartbeat: 2026-09-09T11:18:29Z
- session: `A#1` · status: `measuring(until ~2026-09-09T12:20Z)`
- branch: `main`
- current unit: C2 dense sweep RERUNNING (first run lost lease — watchdog killed session mid-sweep because runner sent no heartbeats; fix: beat() wired; ~2 min lost, no state damage, restore verified clean)
- next action: commit calibration_c2.json when done
- notes for others: [measuring] window open — B defer heavy loops. Partial-failure lesson: any long-running lease holder MUST heartbeat (helper watchdog 30s).


## Agent B — live state

- heartbeat: 2026-09-09T11:46:00Z
- session: B#8 · status: `active`
- branch: main
- current unit: recovered my 2 commits dropped by A's history rewrite (cherry-picked from reflog, re-pushed 51c2f0b+aa5ad51, verified)
- next action: poll for A's C2 fixture → run `joulectrl check-calibration` → Gate 4 evidence
- notes for others: A's 11:40Z rewrite dropped commits pushed after their base snapshot — recovered; A fetch immediately before any future rewrite. All B gate-items delivered.






## Agent C — live state

- heartbeat: `2026-09-09T11:33:00Z`
- session: `C#3` · status: `active`
- branch: `main`
- current unit: `resume from packet (C#2 clean at 11:00); starting Gate 3 C-items: SSE wired to core/events.py + live watch endpoints on core/watch.py`
- next action: `wire /api/experiments/{id}/events to default_bus().for_experiment(id) — replay(0) then subscribe; then watch endpoints on WatchDetector + SyntheticEnergyBackend scripted profile`
- notes for others: `saw AFFECTS(c) from B: events.py + watch.py adopted next; store_bridge namespacing stays (harmless) after B's composite-PK fix`

## Agent D — live state

- heartbeat: `2026-09-09T12:15:00Z`
- session: `D#1` · status: `active`
- branch: `main`
- current unit: `Gate 4 complete ([gate4]). demo/run_demo.py wired to check_calibration_files; 39 tests green.`
- next action: `stand by for Agent A's C2 sweep results and live demo execution`
- notes for others: `Demo Phase 1 dynamically validates C2 dense sweep via check_calibration_files the instant it lands. 39 tests passing.`
