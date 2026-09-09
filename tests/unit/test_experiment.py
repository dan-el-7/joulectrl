"""Tests for the persisted experiment lifecycle."""

import pytest

from core.experiment import ExperimentStateMachine, InvalidTransition
from core.store import Store


@pytest.fixture
def machine():
    store = Store(":memory:")
    store.create_experiment("exp", "fixed_compute")
    return ExperimentStateMachine(store, "exp")


def test_happy_path_and_verified_restoration(machine):
    for state in ("CHECKING", "PREPARING", "PROFILING", "PROFILE_READY", "SELECTED", "VALIDATING", "COMPLETE"):
        machine.transition(state)

    assert machine.restore(lambda: None)
    assert machine.state == "RESTORED"
    assert machine.store.get_experiment("exp")["restoration_status"] == "restored"


def test_invalid_shortcut_is_rejected(machine):
    with pytest.raises(InvalidTransition):
        machine.transition("COMPLETE")


def test_cancellation_enters_restoration_path(machine):
    machine.transition("CHECKING")
    assert machine.cancel(lambda: True)
    assert machine.state == "CANCELLING"
    assert machine.restore(lambda: None)
    assert machine.state == "RESTORED"


def test_failed_restore_is_visible_as_recovery_required(machine):
    machine.transition("CHECKING")
    machine.cancel()

    assert not machine.restore(lambda: (_ for _ in ()).throw(RuntimeError("helper disconnected")))
    assert machine.state == "RECOVERY_REQUIRED"
    assert machine.store.get_experiment("exp")["restoration_status"] == "recovery_required"
