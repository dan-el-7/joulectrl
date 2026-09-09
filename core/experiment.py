"""Explicit, persisted experiment state machine.

The store records transitions; this module prevents callers from inventing unsafe
shortcuts and makes restoration outcome a first-class state visible to the UI.
"""

from __future__ import annotations

from typing import Callable, Optional

from core.store import Store


class InvalidTransition(ValueError):
    """Raised when a caller attempts a transition outside the experiment graph."""


_ALLOWED = {
    "IDLE": {"CHECKING"},
    "CHECKING": {"PREPARING", "FAILED", "CANCELLING"},
    "PREPARING": {"PROFILING", "FAILED", "CANCELLING"},
    "PROFILING": {"PROFILE_READY", "FAILED", "CANCELLING"},
    "PROFILE_READY": {"SELECTED", "CANCELLING"},
    "SELECTED": {"VALIDATING", "CANCELLING"},
    "VALIDATING": {"COMPLETE", "FAILED", "CANCELLING"},
    "COMPLETE": {"RESTORING"},
    "FAILED": {"RESTORING"},
    "CANCELLING": {"RESTORING"},
    "RESTORING": {"RESTORED", "RECOVERY_REQUIRED"},
    "RESTORED": set(),
    "RECOVERY_REQUIRED": set(),
}


class ExperimentStateMachine:
    """Guard the persisted lifecycle for a single experiment."""

    def __init__(self, store: Store, experiment_id: str) -> None:
        self.store = store
        self.experiment_id = experiment_id
        if not self.store.get_experiment(experiment_id):
            raise ValueError(f"Experiment {experiment_id} does not exist")

    @property
    def state(self) -> str:
        experiment = self.store.get_experiment(self.experiment_id)
        assert experiment is not None
        return str(experiment["state"])

    def transition(self, target: str, reason: str = "") -> None:
        if target not in _ALLOWED.get(self.state, set()):
            raise InvalidTransition(f"cannot transition {self.state} -> {target}")
        self.store.transition_state(self.experiment_id, target, reason)

    def fail(self, reason: str) -> None:
        """Record failure, then always enter the restoration path."""
        if self.state not in {"FAILED", "RESTORING", "RESTORED", "RECOVERY_REQUIRED"}:
            self.transition("FAILED", reason)

    def cancel(self, cancel_active_run: Optional[Callable[[], bool]] = None) -> bool:
        """Request workload cancellation and make restoration pending immediately."""
        cancelled = cancel_active_run() if cancel_active_run else False
        if self.state not in {"CANCELLING", "RESTORING", "RESTORED", "RECOVERY_REQUIRED"}:
            self.transition("CANCELLING", "user cancellation requested")
        return cancelled

    def restore(self, restore_settings: Callable[[], None]) -> bool:
        """Invoke the helper-provided restore action and persist its exact outcome."""
        if self.state not in {"RESTORING", "RESTORED", "RECOVERY_REQUIRED"}:
            self.transition("RESTORING", "restoration required")
        self.store.update_restoration_status(self.experiment_id, "restoring")
        try:
            restore_settings()
        except Exception as exc:
            self.store.update_restoration_status(self.experiment_id, "recovery_required")
            if self.state == "RESTORING":
                self.transition("RECOVERY_REQUIRED", f"restore failed: {exc}")
            return False
        self.store.update_restoration_status(self.experiment_id, "restored")
        if self.state == "RESTORING":
            self.transition("RESTORED", "restore verified")
        return True
