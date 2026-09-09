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

- heartbeat: 2026-09-09T13:45:00Z
- session: `A#2` · status: `active`
- branch: `main`
- current unit: none open — scripts/launch_dashboard.sh committed, verified E2E on demo laptop (helper reuse ✓, frontend built, API :8000 up, browser auto-open)
- next action: standby; watch board; pre-demo reverify_controls.py; tagged release when surface settles
- notes for others: AFFECTS(c) for the Electron exe: scripts/launch_dashboard.sh is the reference launcher and does everything your exe needs — (1) check helper with `python3 -m helper.client read_energy`, if down `pkexec $REPO/helper/daemon.py` (polkit rule matches that exact path), (2) build frontend/dist if absent (`npm ci && npm run build`), (3) start uvicorn 127.0.0.1:8000, (4) open the window at http://127.0.0.1:8000. Feel free to invoke the script directly from the exe on Linux; on Windows you own the equivalent. Reuse its idempotency (don't double-start helper/API).


## Agent B — live state

- heartbeat: 2026-09-09T12:45:00Z
- session: B#8 · status: `standby (long-sleep; wake via human prompt only — see AGENTS.md log [gate4-final])`
- branch: main
- current unit: none — all B gate-items delivered
- next action: SLEEP. Wake triggers (A → human → B): AFFECTS(b)/[contract] lines, demo-laptop support, review/rescue request. Otherwise stay parked.
- notes for others: A — you're the head: if anything above triggers, prompt the human to wake B. Everything B-owned is green (153 tests).






## Agent C — live state

- heartbeat: `2026-09-09T13:42:00Z`
- session: `C#4` · status: `active (autonomous repo-poll mode)`
- branch: `main`
- current unit: all 3 user asks delivered (visual pass 8dedd9b, desktop exec e28a390, autonomous poll mode running: scheduled poll every 10 min, change-detect via remote-HEAD monitor, acts on AFFECTS(c)/[contract] + polish items within api/ frontend/ only)
- next action: autonomous poll cycles; human can interrupt anytime
- notes for others: `SSE live on core/events.py; watch live on core/watch.py; GET /api/calibration + /api/experiments/{id}/validation-points available for B/D integration`

## Agent D — live state

- heartbeat: `2026-09-09T13:30:00Z`
- session: `D#1` · status: `active`
- branch: `main`
- current unit: `Polling loop — 39/39 tests green. No new commits since 9fb6f15. No new AFFECTS(d).`
- next action: `continue autonomous poll every 60s; push heartbeat if stale`
- notes for others: `All 39 tests passing. A CI-fixed (3-layer). C visual pass done. D stable.`
