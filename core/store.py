"""core/store.py — SQLite persistence and JSON export for joulectrl (Agent B owned).

Stores:
- Experiments and state transitions (PLAN Section 8)
- RunRecord items (both harness and watch mode)
- CalibrationRecord items
- Profile and Selection snapshots
- Restorations and safety audits
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from core.models import (
    CalibrationRecord,
    Configuration,
    Profile,
    RunRecord,
    Selection,
    ValidationPair,
    utc_now_iso,
)

DEFAULT_DB_PATH: str = os.path.join(os.path.expanduser("~"), ".joulectrl", "joulectrl.db")


class Store:
    """SQLite-backed persistent store for joulectrl."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        if self.db_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        """Create database tables if they do not exist."""
        with self.conn:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    id TEXT PRIMARY KEY,
                    workload_name TEXT NOT NULL,
                    objective TEXT NOT NULL DEFAULT 'deadline',
                    state TEXT NOT NULL DEFAULT 'IDLE',
                    runtime_budget_s REAL,
                    preference_json TEXT,
                    restoration_status TEXT NOT NULL DEFAULT 'not_required',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    profile_json TEXT,
                    selection_json TEXT,
                    validation_json TEXT,
                    metadata_json TEXT
                );

                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    config_id TEXT NOT NULL,
                    workload_name TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'harness',
                    phase TEXT NOT NULL DEFAULT 'profiling',
                    repetition INTEGER NOT NULL,
                    runtime_s REAL NOT NULL,
                    package_energy_j REAL,
                    energy_available INTEGER NOT NULL,
                    avg_power_w REAL,
                    status TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (experiment_id) REFERENCES experiments (id)
                );

                CREATE TABLE IF NOT EXISTS state_transitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    experiment_id TEXT NOT NULL,
                    from_state TEXT NOT NULL,
                    to_state TEXT NOT NULL,
                    reason TEXT,
                    timestamp_iso TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS calibrations (
                    calibration_id TEXT PRIMARY KEY,
                    core_class TEXT NOT NULL,
                    layout TEXT NOT NULL,
                    phase TEXT NOT NULL DEFAULT 'calibration',
                    repetition INTEGER NOT NULL,
                    runtime_s REAL NOT NULL,
                    package_energy_j REAL,
                    energy_available INTEGER NOT NULL,
                    throughput REAL NOT NULL,
                    scaling_efficiency REAL,
                    kernel_checksum TEXT NOT NULL,
                    machine_fingerprint TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_runs_exp ON runs (experiment_id);
                CREATE INDEX IF NOT EXISTS idx_transitions_exp ON state_transitions (experiment_id);
                CREATE INDEX IF NOT EXISTS idx_cal_fingerprint ON calibrations (machine_fingerprint);
                """
            )

    def close(self) -> None:
        """Close sqlite connection."""
        self.conn.close()

    # -----------------------------------------------------------------------
    # Experiments & State Machine
    # -----------------------------------------------------------------------

    def create_experiment(
        self,
        experiment_id: str,
        workload_name: str,
        objective: str = "deadline",
        runtime_budget_s: Optional[float] = None,
        preference: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Create and initialize a new experiment."""
        now = utc_now_iso()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO experiments (
                    id, workload_name, objective, state, runtime_budget_s,
                    preference_json, restoration_status, created_at, updated_at, metadata_json
                ) VALUES (?, ?, ?, 'IDLE', ?, ?, 'not_required', ?, ?, ?)
                """,
                (
                    experiment_id,
                    workload_name,
                    objective,
                    runtime_budget_s,
                    json.dumps(preference) if preference else None,
                    now,
                    now,
                    json.dumps(metadata) if metadata else None,
                ),
            )
        self.record_state_transition(experiment_id, "NONE", "IDLE", "Experiment created")
        return self.get_experiment(experiment_id)  # type: ignore

    def transition_state(self, experiment_id: str, to_state: str, reason: str = "") -> None:
        """Update experiment state and record the transition."""
        exp = self.get_experiment(experiment_id)
        if not exp:
            raise ValueError(f"Experiment {experiment_id} does not exist")
        from_state = exp["state"]
        now = utc_now_iso()
        with self.conn:
            self.conn.execute(
                "UPDATE experiments SET state = ?, updated_at = ? WHERE id = ?",
                (to_state, now, experiment_id),
            )
        self.record_state_transition(experiment_id, from_state, to_state, reason)

    def record_state_transition(
        self, experiment_id: str, from_state: str, to_state: str, reason: str = ""
    ) -> None:
        """Record an immutable state transition row."""
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO state_transitions (experiment_id, from_state, to_state, reason, timestamp_iso)
                VALUES (?, ?, ?, ?, ?)
                """,
                (experiment_id, from_state, to_state, reason, utc_now_iso()),
            )

    def get_state_transitions(self, experiment_id: str) -> list[dict[str, Any]]:
        """List state transitions for an experiment."""
        cur = self.conn.execute(
            "SELECT * FROM state_transitions WHERE experiment_id = ? ORDER BY id ASC",
            (experiment_id,),
        )
        return [dict(row) for row in cur.fetchall()]

    def update_restoration_status(self, experiment_id: str, status: str) -> None:
        """Update restoration status ('not_required', 'restoring', 'restored', 'recovery_required')."""
        with self.conn:
            self.conn.execute(
                "UPDATE experiments SET restoration_status = ?, updated_at = ? WHERE id = ?",
                (status, utc_now_iso(), experiment_id),
            )

    def save_profile(self, profile: Profile) -> None:
        """Store computed Profile for an experiment."""
        with self.conn:
            self.conn.execute(
                "UPDATE experiments SET profile_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(profile.to_dict()), utc_now_iso(), profile.experiment_id),
            )

    def save_selection(self, selection: Selection) -> None:
        """Store Selection outcome for an experiment."""
        with self.conn:
            self.conn.execute(
                "UPDATE experiments SET selection_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(selection.to_dict()), utc_now_iso(), selection.experiment_id),
            )

    def save_validation_pairs(self, experiment_id: str, pairs: list[ValidationPair]) -> None:
        """Store validation pairs for an experiment."""
        pairs_data = [p.to_dict() for p in pairs]
        with self.conn:
            self.conn.execute(
                "UPDATE experiments SET validation_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(pairs_data), utc_now_iso(), experiment_id),
            )

    def get_experiment(self, experiment_id: str) -> Optional[dict[str, Any]]:
        """Get experiment dictionary with decoded JSON fields."""
        cur = self.conn.execute("SELECT * FROM experiments WHERE id = ?", (experiment_id,))
        row = cur.fetchone()
        if not row:
            return None
        res = dict(row)
        res["preference"] = json.loads(res["preference_json"]) if res.get("preference_json") else None
        res["profile"] = json.loads(res["profile_json"]) if res.get("profile_json") else None
        res["selection"] = json.loads(res["selection_json"]) if res.get("selection_json") else None
        res["validation"] = json.loads(res["validation_json"]) if res.get("validation_json") else []
        res["metadata"] = json.loads(res["metadata_json"]) if res.get("metadata_json") else {}
        res["state_transitions"] = self.get_state_transitions(experiment_id)
        return res

    def list_experiments(self) -> list[dict[str, Any]]:
        """List summary of all experiments."""
        cur = self.conn.execute("SELECT id, workload_name, objective, state, created_at, updated_at FROM experiments ORDER BY created_at DESC")
        return [dict(row) for row in cur.fetchall()]

    # -----------------------------------------------------------------------
    # Run Records
    # -----------------------------------------------------------------------

    def record_run(self, run: RunRecord) -> None:
        """Persist a RunRecord."""
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO runs (
                    run_id, experiment_id, config_id, workload_name, mode, phase,
                    repetition, runtime_s, package_energy_j, energy_available,
                    avg_power_w, status, data_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.experiment_id,
                    run.config_id,
                    run.workload_name,
                    run.mode,
                    run.phase,
                    run.repetition,
                    run.runtime_s,
                    run.package_energy_j,
                    1 if run.energy_available else 0,
                    run.avg_power_w,
                    run.status,
                    json.dumps(run.to_dict()),
                    run.timestamp_iso or utc_now_iso(),
                ),
            )

    def get_runs(self, experiment_id: str) -> list[RunRecord]:
        """Fetch all RunRecords for an experiment."""
        cur = self.conn.execute(
            "SELECT data_json FROM runs WHERE experiment_id = ? ORDER BY repetition ASC",
            (experiment_id,),
        )
        return [RunRecord.from_dict(json.loads(row["data_json"])) for row in cur.fetchall()]

    # -----------------------------------------------------------------------
    # Calibration Records
    # -----------------------------------------------------------------------

    def record_calibration(self, cal: CalibrationRecord) -> None:
        """Persist a CalibrationRecord."""
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO calibrations (
                    calibration_id, core_class, layout, phase, repetition,
                    runtime_s, package_energy_j, energy_available, throughput,
                    scaling_efficiency, kernel_checksum, machine_fingerprint,
                    data_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cal.calibration_id,
                    cal.core_class,
                    cal.layout,
                    cal.phase,
                    cal.repetition,
                    cal.runtime_s,
                    cal.package_energy_j,
                    1 if cal.energy_available else 0,
                    cal.throughput,
                    cal.scaling_efficiency,
                    cal.kernel_checksum,
                    cal.machine_fingerprint,
                    json.dumps(cal.to_dict()),
                    cal.timestamp_iso or utc_now_iso(),
                ),
            )

    def get_calibrations(self, machine_fingerprint: Optional[str] = None) -> list[CalibrationRecord]:
        """Fetch CalibrationRecords, optionally filtered by machine fingerprint."""
        if machine_fingerprint:
            cur = self.conn.execute(
                "SELECT data_json FROM calibrations WHERE machine_fingerprint = ? ORDER BY core_class ASC, created_at ASC",
                (machine_fingerprint,),
            )
        else:
            cur = self.conn.execute("SELECT data_json FROM calibrations ORDER BY core_class ASC, created_at ASC")
        return [CalibrationRecord.from_dict(json.loads(row["data_json"])) for row in cur.fetchall()]

    # -----------------------------------------------------------------------
    # Export
    # -----------------------------------------------------------------------

    def export_experiment(self, experiment_id: str) -> dict[str, Any]:
        """Generate full, auditable JSON archive of an experiment."""
        exp = self.get_experiment(experiment_id)
        if not exp:
            raise ValueError(f"Experiment {experiment_id} not found")
        runs = [r.to_dict() for r in self.get_runs(experiment_id)]
        exp["runs"] = runs
        return exp

    def export_experiment_json(self, experiment_id: str, file_path: Optional[str] = None) -> str:
        """Export experiment as formatted JSON string or file."""
        data = self.export_experiment(experiment_id)
        dumped = json.dumps(data, indent=2)
        if file_path:
            os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(dumped)
        return dumped
