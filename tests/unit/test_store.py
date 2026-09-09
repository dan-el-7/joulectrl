"""Unit tests for core/store.py SQLite persistence."""

import os
import tempfile
import pytest

from core.models import (
    CalibrationRecord,
    ConfigSummary,
    Configuration,
    Profile,
    RunRecord,
    Selection,
    ValidationPair,
)
from core.store import Store


@pytest.fixture
def store():
    """In-memory SQLite store for tests."""
    return Store(":memory:")


def test_experiment_lifecycle_and_transitions(store):
    exp = store.create_experiment(
        experiment_id="exp-1",
        workload_name="clean_build",
        objective="deadline",
        runtime_budget_s=45.0,
    )
    assert exp["id"] == "exp-1"
    assert exp["state"] == "IDLE"

    # State transitions
    store.transition_state("exp-1", "CHECKING", "Environment verification")
    store.transition_state("exp-1", "PROFILING", "Starting sweep")
    store.transition_state("exp-1", "COMPLETE", "Runs finished")

    transitions = store.get_state_transitions("exp-1")
    # Transitions: NONE->IDLE, IDLE->CHECKING, CHECKING->PROFILING, PROFILING->COMPLETE
    assert len(transitions) == 4
    assert transitions[-1]["to_state"] == "COMPLETE"

    # Restoration status
    store.update_restoration_status("exp-1", "restored")
    updated = store.get_experiment("exp-1")
    assert updated["restoration_status"] == "restored"


def test_run_records_persistence(store):
    store.create_experiment(experiment_id="exp-2", workload_name="clean_build")

    r1 = RunRecord(
        run_id="run-1",
        experiment_id="exp-2",
        config_id="stock",
        workload_name="clean_build",
        repetition=1,
        runtime_s=10.5,
        package_energy_j=500.0,
    )
    r2 = RunRecord(
        run_id="run-2",
        experiment_id="exp-2",
        config_id="stock",
        workload_name="clean_build",
        repetition=2,
        runtime_s=10.4,
        package_energy_j=495.0,
    )
    store.record_run(r1)
    store.record_run(r2)

    runs = store.get_runs("exp-2")
    assert len(runs) == 2
    assert runs[0].run_id == "run-1"
    assert runs[0].package_energy_j == 500.0
    assert runs[1].run_id == "run-2"


def test_calibration_records_persistence(store):
    cal = CalibrationRecord(
        calibration_id="cal-1",
        core_class="fast",
        layout="C2",
        cpus=[0, 2, 4, 6],
        requested_control={"cap_khz": 3000000, "boost": False},
        accepted_control={"cap_khz": 3000000, "boost": False},
        runtime_s=5.0,
        package_energy_j=120.0,
        work_units=10000.0,
        kernel_checksum="0x3a762069507139ac",
        machine_fingerprint="boot-fedora-1",
    )
    store.record_calibration(cal)

    results = store.get_calibrations(machine_fingerprint="boot-fedora-1")
    assert len(results) == 1
    assert results[0].calibration_id == "cal-1"
    assert results[0].kernel_checksum == "0x3a762069507139ac"
    assert results[0].accepted_control["boost"] is False


def test_profile_and_selection_and_export(store):
    store.create_experiment(experiment_id="exp-3", workload_name="clean_build")

    cfg = Configuration(id="stock", layout="all", worker_count=16)
    summary = ConfigSummary(
        config_id="stock",
        configuration=cfg,
        runtime_samples=[10.0],
        energy_samples=[500.0],
        median_runtime_s=10.0,
        median_energy_j=500.0,
    )
    profile = Profile(
        experiment_id="exp-3",
        workload_name="clean_build",
        baseline_config_id="stock",
        configurations={"stock": summary},
    )
    store.save_profile(profile)

    selection = Selection(
        experiment_id="exp-3",
        objective_mode="deadline",
        status="selected",
        status_message="Optimized",
        selected_config_id="stock",
    )
    store.save_selection(selection)

    exported = store.export_experiment("exp-3")
    assert exported["id"] == "exp-3"
    assert exported["profile"]["baseline_config_id"] == "stock"
    assert exported["selection"]["status"] == "selected"
