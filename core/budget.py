"""Suggested-budget computation from watch segments (AGENTS.md §6b, Agent B).

Turns observed idle→activity→idle segments into a single runtime budget that
pre-fills the Setup slider. Deterministic and honest:

- The budget is a *suggestion* built from estimated measurements; it never
  enters selection evidence (segments are mode="watch").
- Single-segment case: budget = runtime * (1 + slack). The API doc's canonical
  example (runtime 47.0 s -> suggested 49.35 s = +5%) fixes the default slack
  at 5%. Detection uncertainty (one poll interval) is *displayed separately*
  on the segment label per §6b — it is not silently folded into the budget.
- Multi-segment case: segments are independent task executions (long idle
  separates them; never auto-merged). The budget should cover a *typical* run,
  not the slowest ever observed — use the median runtime so one outlier
  (machine noise, background interference) cannot inflate the slider.
- Runtime is always available; energy is contextual only and never gates the
  suggestion (watch energy is an estimate).
"""

from __future__ import annotations

from statistics import median
from typing import Optional, Sequence

from core.watch import WatchSegment

# Slack added on top of the representative runtime, as a fraction. The frozen
# API example (47.0 s -> 49.35 s) fixes 5%.
DEFAULT_SLACK = 0.05


def suggest_budget(
    segments: Sequence[WatchSegment],
    *,
    slack: float = DEFAULT_SLACK,
) -> Optional[float]:
    """Suggested runtime budget (seconds) from observed watch segments.

    Returns None when there are no completed segments (nothing observed yet —
    never invent a number).
    """
    runtimes = [s.runtime_s for s in segments if s.runtime_s > 0]
    if not runtimes:
        return None
    representative = median(runtimes) if len(runtimes) > 1 else runtimes[0]
    budget = representative * (1.0 + slack)
    return round(budget, 2)
