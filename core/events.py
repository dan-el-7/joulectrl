"""In-process live event feed for experiments (Agent B owned).

Bridges the runner / state machine / validation loop to the frozen SSE event
contract (docs/API.md §4.1) without coupling core to the API layer:

- ``EventBus`` — process-wide registry of per-experiment ``ExperimentEvents``
  logs. Thread-safe; publishes to synchronous subscribers only (the API layer
  bridges to async SSE itself).
- Event names are exactly the frozen contract: ``experiment_state``,
  ``run_progress``, ``run_complete``, ``profile_ready``, ``selection_updated``,
  ``restore_status``.
- Every event is appended to a bounded per-experiment history so a subscriber
  can replay from index 0 and then follow live — C's SSE endpoint currently
  reconstructs events from the store; this gives it one authoritative source.
- Publishing is best-effort: a raising subscriber never breaks the experiment
  (the run always wins over the dashboard).
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

EVENT_NAMES = frozenset(
    {
        "experiment_state",
        "run_progress",
        "run_complete",
        "profile_ready",
        "selection_updated",
        "restore_status",
        "validation_progress",
        "validation_pair_complete",
        "validation_complete",
    }
)

MAX_HISTORY = 10_000


def _timestamp_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass(frozen=True)
class Event:
    experiment_id: str
    name: str
    payload: dict
    timestamp: str = field(default_factory=_timestamp_iso)
    seq: int = 0

    def sse_frame(self) -> str:
        """Render as a standard SSE frame (docs/API.md §4)."""
        data = dict(self.payload)
        if self.name == "experiment_state":
            data.setdefault("experiment_id", self.experiment_id)
            data.setdefault("timestamp", self.timestamp)
        elif self.name == "restore_status":
            data.setdefault("timestamp", self.timestamp)
        return f"event: {self.name}\ndata: {json.dumps(data)}\n\n"


class ExperimentEvents:
    """Bounded event log + fan-out for one experiment."""

    def __init__(self, experiment_id: str) -> None:
        self.experiment_id = experiment_id
        self._lock = threading.Lock()
        self._history: list[Event] = []
        self._subscribers: list[Callable[[Event], None]] = []
        self._seq = 0

    def publish(self, name: str, payload: Optional[dict] = None) -> Event:
        if name not in EVENT_NAMES:
            raise ValueError(f"unknown SSE event name {name!r}")
        with self._lock:
            self._seq += 1
            event = Event(
                experiment_id=self.experiment_id,
                name=name,
                payload=dict(payload or {}),
                seq=self._seq,
            )
            if len(self._history) >= MAX_HISTORY:
                self._history = self._history[-MAX_HISTORY // 2 :]
            self._history.append(event)
            subscribers = list(self._subscribers)
        # Deliver outside the lock; a slow/raising subscriber must not block.
        for subscriber in subscribers:
            try:
                subscriber(event)
            except Exception:
                pass  # dashboard failures never break the experiment
        return event

    def subscribe(self, callback: Callable[[Event], None]) -> Callable[[], None]:
        with self._lock:
            self._subscribers.append(callback)

        def unsubscribe() -> None:
            with self._lock:
                if callback in self._subscribers:
                    self._subscribers.remove(callback)

        return unsubscribe

    def replay(self, from_seq: int = 0) -> list[Event]:
        """All events with seq > from_seq (0 replays everything)."""
        with self._lock:
            return [e for e in self._history if e.seq > from_seq]

    def last_seq(self) -> int:
        with self._lock:
            return self._seq


class EventBus:
    """Process-wide registry; one ExperimentEvents per experiment id."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._logs: dict[str, ExperimentEvents] = {}

    def for_experiment(self, experiment_id: str) -> ExperimentEvents:
        with self._lock:
            log = self._logs.get(experiment_id)
            if log is None:
                log = ExperimentEvents(experiment_id)
                self._logs[experiment_id] = log
            return log

    def publish(self, experiment_id: str, name: str, payload: Optional[dict] = None) -> Event:
        return self.for_experiment(experiment_id).publish(name, payload)


_default_bus: Optional[EventBus] = None
_default_bus_lock = threading.Lock()


def default_bus() -> EventBus:
    global _default_bus
    with _default_bus_lock:
        if _default_bus is None:
            _default_bus = EventBus()
        return _default_bus
