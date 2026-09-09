"""Tests for core/events.py and the state machine's live event wiring."""

from __future__ import annotations

import threading

import pytest

from core.events import Event, EventBus, default_bus
from core.experiment import ExperimentStateMachine
from core.models import Configuration
from core.store import Store
from tests.unit.test_runner import PythonWorkload, SequenceEnergy, config as test_config  # noqa: F401


class RecordingRunner:
    """Minimal runner double returning a fixed successful record."""

    def __init__(self, runtime_s: float = 1.0, energy_j: float = 10.0) -> None:
        self.runtime_s = runtime_s
        self.energy_j = energy_j
        self.calls = 0

    def run(self, workload, experiment_id, configuration, repetition, **kwargs):
        from core.models import RunRecord

        self.calls += 1
        return RunRecord(
            run_id=f"run-{self.calls}",
            experiment_id=experiment_id,
            config_id=configuration.id,
            workload_name="python-test",
            repetition=repetition,
            phase="profiling",
            start_time_monotonic=0.0,
            end_time_monotonic=self.runtime_s,
            runtime_s=self.runtime_s,
            package_energy_j=self.energy_j,
            energy_available=True,
            status="success",
            output_verified=True,
            configuration=configuration,
        )


def test_publish_rejects_unknown_event_name():
    bus = EventBus()
    log = bus.for_experiment("exp-x")
    with pytest.raises(ValueError):
        log.publish("not_a_contract_event", {})


def test_history_replay_and_subscribe():
    bus = EventBus()
    log = bus.for_experiment("exp-y")
    log.publish("experiment_state", {"state": "IDLE"})
    log.publish("experiment_state", {"state": "CHECKING"})

    assert [e.seq for e in log.replay(0)] == [1, 2]
    assert [e.seq for e in log.replay(1)] == [2]

    received: list[Event] = []
    unsubscribe = log.subscribe(received.append)
    log.publish("run_progress", {"phase": "profiling"})
    unsubscribe()
    log.publish("run_complete", {})
    assert [e.name for e in received] == ["run_progress"]


def test_raising_subscriber_never_breaks_publish():
    log = EventBus().for_experiment("exp-z")
    log.subscribe(lambda e: (_ for _ in ()).throw(RuntimeError("boom")))
    event = log.publish("profile_ready", {"configurations_count": 3})
    assert event.name == "profile_ready"


def test_sse_frame_matches_contract_shape():
    log = EventBus().for_experiment("exp-frame")
    event = log.publish(
        "experiment_state", {"state": "PROFILING", "previous_state": "PREPARING", "message": "m"}
    )
    frame = event.sse_frame()
    assert frame.startswith("event: experiment_state\ndata: ")
    assert frame.endswith("\n\n")
    import json

    data = json.loads(frame.split("data: ", 1)[1].strip())
    assert data["experiment_id"] == "exp-frame"
    assert data["state"] == "PROFILING"
    assert "timestamp" in data


def test_thread_safety_smoke():
    log = EventBus().for_experiment("exp-threads")
    seen: list[int] = []
    log.subscribe(seen.append)

    def worker() -> None:
        for _ in range(200):
            log.publish("run_progress", {})

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert log.last_seq() == 800
    assert len(seen) == 800


def test_state_machine_emits_contract_events(tmp_path):
    store = Store(":memory:")
    store.create_experiment(experiment_id="exp-evt", workload_name="clean_build")
    machine = ExperimentStateMachine(store, "exp-evt")
    log = machine.events
    names: list[str] = []
    log.subscribe(lambda e: names.append(e.name))

    record = machine.run_profile_point(
        RecordingRunner(), PythonWorkload("print('ok')"), test_config(), 1
    )
    assert record.status == "success"
    assert names == [
        "experiment_state",  # CHECKING
        "experiment_state",  # PREPARING
        "experiment_state",  # PROFILING
        "run_progress",
        "run_complete",
        "experiment_state",  # PROFILE_READY
    ]
    run_complete = [e for e in log.replay(0) if e.name == "run_complete"][0]
    assert run_complete.payload["run_record"]["runtime_s"] == 1.0


def test_restore_emits_restore_status_events(tmp_path):
    store = Store(":memory:")
    store.create_experiment(experiment_id="exp-rst", workload_name="clean_build")
    machine = ExperimentStateMachine(store, "exp-rst")
    log = machine.events

    assert machine.restore(lambda: None) is True
    statuses = [e.payload["status"] for e in log.replay(0) if e.name == "restore_status"]
    assert statuses == ["restoring", "restored"]
    states = [e.payload["state"] for e in log.replay(0) if e.name == "experiment_state"]
    assert states == ["RESTORING", "RESTORED"]

    store.create_experiment(experiment_id="exp-rst-2", workload_name="clean_build")
    failed = ExperimentStateMachine(store, "exp-rst-2")
    assert failed.restore(lambda: (_ for _ in ()).throw(RuntimeError("nope"))) is False
    statuses2 = [e.payload["status"] for e in failed.events.replay(0) if e.name == "restore_status"]
    assert statuses2 == ["restoring", "recovery_required"]


def test_default_bus_is_shared():
    assert default_bus() is default_bus()
