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


def test_same_run_id_in_different_experiments_is_not_clobbered(store):
    """C's AFFECTS(b): identical run_ids across experiments must stay separate."""
    store.create_experiment(experiment_id="exp-a", workload_name="clean_build")
    store.create_experiment(experiment_id="exp-b", workload_name="clean_build")
    for exp, energy in (("exp-a", 100.0), ("exp-b", 900.0)):
        store.record_run(
            RunRecord(
                run_id="cfg_stock_r1",
                experiment_id=exp,
                config_id="stock",
                workload_name="clean_build",
                repetition=1,
                runtime_s=10.0,
                package_energy_j=energy,
            )
        )
    assert len(store.get_runs("exp-a")) == 1
    assert store.get_runs("exp-a")[0].package_energy_j == 100.0
    assert len(store.get_runs("exp-b")) == 1
    assert store.get_runs("exp-b")[0].package_energy_j == 900.0


def test_legacy_run_id_primary_key_database_migrates(tmp_path):
    """A legacy DB with run_id-only PK is migrated to (experiment_id, run_id)."""
    import sqlite3

    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE experiments (
            id TEXT PRIMARY KEY, workload_name TEXT NOT NULL,
            objective TEXT NOT NULL DEFAULT 'deadline',
            state TEXT NOT NULL DEFAULT 'IDLE', runtime_budget_s REAL,
            preference_json TEXT,
            restoration_status TEXT NOT NULL DEFAULT 'not_required',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            profile_json TEXT, selection_json TEXT, validation_json TEXT,
            metadata_json TEXT
        );
        CREATE TABLE runs (
            run_id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL,
            config_id TEXT NOT NULL, workload_name TEXT NOT NULL,
            mode TEXT NOT NULL DEFAULT 'harness',
            phase TEXT NOT NULL DEFAULT 'profiling',
            repetition INTEGER NOT NULL, runtime_s REAL NOT NULL,
            package_energy_j REAL, energy_available INTEGER NOT NULL,
            avg_power_w REAL, status TEXT NOT NULL,
            data_json TEXT NOT NULL, created_at TEXT NOT NULL
        );
        """
    )
    conn.execute(
        "INSERT INTO experiments (id, workload_name, created_at, updated_at) "
        "VALUES ('exp-old', 'clean_build', '2026-09-09T00:00:00Z', '2026-09-09T00:00:00Z')"
    )
    import json as _json

    full_record = {
        "run_id": "run-old", "experiment_id": "exp-old", "config_id": "stock",
        "workload_name": "clean_build", "repetition": 1, "phase": "profiling",
        "start_time_monotonic": 0.0, "end_time_monotonic": 10.0,
        "runtime_s": 10.0, "package_energy_j": 500.0, "energy_available": True,
        "status": "success", "output_verified": True,
    }
    conn.execute(
        "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "run-old", "exp-old", "stock", "clean_build", "harness",
            "profiling", 1, 10.0, 500.0, 1, 50.0, "success",
            _json.dumps(full_record), "2026-09-09T00:00:00Z",
        ),
    )
    conn.commit()
    conn.close()

    migrated = Store(str(db_path))
    runs = migrated.get_runs("exp-old")
    assert len(runs) == 1
    assert runs[0].run_id == "run-old"
    # New composite-key writes work on the migrated DB.
    migrated.create_experiment(experiment_id="exp-new", workload_name="clean_build")
    migrated.record_run(
        RunRecord(
            run_id="run-old",  # same id, different experiment
            experiment_id="exp-new",
            config_id="stock",
            workload_name="clean_build",
            repetition=1,
            runtime_s=1.0,
            package_energy_j=1.0,
        )
    )
    assert len(migrated.get_runs("exp-old")) == 1
    assert len(migrated.get_runs("exp-new")) == 1


def test_user_preferences(store):
    assert store.get_preference("energy_savings_opt_in", False) is False
    store.set_preference("energy_savings_opt_in", True)
    assert store.get_preference("energy_savings_opt_in") is True
    store.set_preference("custom_key", {"threshold": 12.5, "enabled": True})
    assert store.get_preference("custom_key") == {"threshold": 12.5, "enabled": True}


def test_savings_ledger_opt_in_gate(store):
    # By default, opt-in is False, so record_savings_entry returns None and doesn't write
    entry = {
        "session_id": "test_1",
        "source": "watch",
        "workload_name": "build",
        "runtime_s": 10.0,
        "stock_energy_j": 300.0,
        "optimized_energy_j": 120.0,
        "saved_energy_j": 180.0,
        "saved_pct": 60.0,
    }
    row_id = store.record_savings_entry(entry, enforce_opt_in=True)
    assert row_id is None
    assert len(store.get_savings_ledger()) == 0

    # Opt-in enabled
    store.set_preference("energy_savings_opt_in", True)
    row_id = store.record_savings_entry(entry, enforce_opt_in=True)
    assert row_id is not None

    ledger = store.get_savings_ledger()
    assert len(ledger) == 1
    assert ledger[0]["session_id"] == "test_1"
    assert ledger[0]["saved_energy_j"] == 180.0
    assert ledger[0]["saved_avg_power_w"] == 18.0  # 180 J / 10s

    summary = store.get_savings_summary()
    assert summary["sessions_count"] == 1
    assert summary["total_runtime_s"] == 10.0
    assert summary["total_saved_energy_j"] == 180.0
    assert summary["total_saved_energy_wh"] == 0.05  # 180 / 3600
    assert summary["avg_watts_saved"] == 18.0

    # Reset ledger
    deleted = store.reset_savings_ledger()
    assert deleted == 1
    assert len(store.get_savings_ledger()) == 0
    assert store.get_savings_summary()["sessions_count"] == 0

