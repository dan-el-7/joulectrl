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
                    experiment_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
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
                    PRIMARY KEY (experiment_id, run_id),
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

                CREATE TABLE IF NOT EXISTS savings_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    workload_name TEXT,
                    app_name TEXT,
                    target_pid INTEGER,
                    objective TEXT,
                    runtime_s REAL NOT NULL,
                    stock_energy_j REAL NOT NULL,
                    optimized_energy_j REAL NOT NULL,
                    saved_energy_j REAL NOT NULL,
                    saved_pct REAL NOT NULL,
                    stock_avg_power_w REAL,
                    optimized_avg_power_w REAL,
                    saved_avg_power_w REAL,
                    timestamp_iso TEXT NOT NULL,
                    metadata_json TEXT
                );

                CREATE TABLE IF NOT EXISTS user_preferences (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_runs_exp ON runs (experiment_id);
                CREATE INDEX IF NOT EXISTS idx_transitions_exp ON state_transitions (experiment_id);
                CREATE INDEX IF NOT EXISTS idx_cal_fingerprint ON calibrations (machine_fingerprint);
                CREATE INDEX IF NOT EXISTS idx_savings_timestamp ON savings_ledger (timestamp_iso);
                """
            )
        if self.db_path != ":memory:":
            try:
                self.conn.execute("PRAGMA journal_mode=WAL;")
                self.conn.execute("PRAGMA synchronous=NORMAL;")
            except Exception:
                pass
        self._migrate_runs_composite_key()

    def _migrate_runs_composite_key(self) -> None:
        """Migrate legacy `runs` tables keyed on run_id alone to (experiment_id, run_id).

        Legacy rows with duplicate run_ids across experiments were already
        collapsed by INSERT OR REPLACE; surviving rows are kept as-is (one per
        run_id) and copied into the new schema.
        """
        cur = self.conn.execute("PRAGMA table_info(runs)")
        columns = {row["name"] for row in cur.fetchall()}
        if not columns or "experiment_id" not in columns:
            return
        pk_cols = [
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(runs)")
            if row["pk"]
        ]
        if pk_cols == ["experiment_id", "run_id"]:
            return
        with self.conn:
            self.conn.executescript(
                """
                ALTER TABLE runs RENAME TO runs_legacy;
                CREATE TABLE runs (
                    experiment_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
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
                    PRIMARY KEY (experiment_id, run_id),
                    FOREIGN KEY (experiment_id) REFERENCES experiments (id)
                );
                INSERT INTO runs SELECT experiment_id, run_id, config_id,
                    workload_name, mode, phase, repetition, runtime_s,
                    package_energy_j, energy_available, avg_power_w, status,
                    data_json, created_at FROM runs_legacy;
                DROP TABLE runs_legacy;
                CREATE INDEX IF NOT EXISTS idx_runs_exp ON runs (experiment_id);
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

    # -----------------------------------------------------------------------
    # User Preferences (Opt-in & Settings)
    # -----------------------------------------------------------------------

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Retrieve a stored user preference by key."""
        cur = self.conn.execute("SELECT value_json FROM user_preferences WHERE key = ?", (key,))
        row = cur.fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value_json"])
        except Exception:
            return default

    def set_preference(self, key: str, value: Any) -> None:
        """Store or update a user preference by key."""
        now = utc_now_iso()
        val_json = json.dumps(value)
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO user_preferences (key, value_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at
                """,
                (key, val_json, now),
            )

    # -----------------------------------------------------------------------
    # Energy Savings Ledger & Analytics
    # -----------------------------------------------------------------------

    def record_savings_entry(
        self, entry: dict[str, Any], enforce_opt_in: bool = True
    ) -> Optional[int]:
        """Record an energy savings receipt to the persistent ledger.

        Args:
            entry: Dict containing session_id, source, workload_name, app_name,
                   target_pid, objective, runtime_s, stock_energy_j,
                   optimized_energy_j, saved_energy_j, saved_pct, stock_avg_power_w,
                   optimized_avg_power_w, saved_avg_power_w, metadata.
            enforce_opt_in: If True, checks if 'energy_savings_opt_in' is enabled
                            before writing. Returns None if disabled.
        """
        if enforce_opt_in and not self.get_preference("energy_savings_opt_in", False):
            return None

        now = entry.get("timestamp_iso") or utc_now_iso()
        runtime_s = float(entry.get("runtime_s", 0.0))
        stock_j = float(entry.get("stock_energy_j", 0.0))
        opt_j = float(entry.get("optimized_energy_j", 0.0))
        saved_j = float(entry.get("saved_energy_j", max(0.0, stock_j - opt_j)))
        saved_pct = float(entry.get("saved_pct", 0.0))

        stock_w = entry.get("stock_avg_power_w")
        if stock_w is None and runtime_s > 0:
            stock_w = stock_j / runtime_s
        opt_w = entry.get("optimized_avg_power_w")
        if opt_w is None and runtime_s > 0:
            opt_w = opt_j / runtime_s
        saved_w = entry.get("saved_avg_power_w")
        if saved_w is None and runtime_s > 0:
            saved_w = saved_j / runtime_s

        meta = entry.get("metadata") or {}

        with self.conn:
            cur = self.conn.execute(
                """
                INSERT INTO savings_ledger (
                    session_id, source, workload_name, app_name, target_pid, objective,
                    runtime_s, stock_energy_j, optimized_energy_j, saved_energy_j,
                    saved_pct, stock_avg_power_w, optimized_avg_power_w,
                    saved_avg_power_w, timestamp_iso, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(entry.get("session_id", "sess_0")),
                    str(entry.get("source", "watch")),
                    entry.get("workload_name"),
                    entry.get("app_name"),
                    entry.get("target_pid"),
                    entry.get("objective"),
                    round(runtime_s, 2),
                    round(stock_j, 2),
                    round(opt_j, 2),
                    round(saved_j, 2),
                    round(saved_pct, 1),
                    round(stock_w, 2) if stock_w is not None else None,
                    round(opt_w, 2) if opt_w is not None else None,
                    round(saved_w, 2) if saved_w is not None else None,
                    now,
                    json.dumps(meta) if meta else None,
                ),
            )
            return cur.lastrowid

    def get_savings_summary(self) -> dict[str, Any]:
        """Compute aggregated energy savings statistics from the ledger."""
        cur = self.conn.execute(
            """
            SELECT
                COUNT(*) as sessions_count,
                COALESCE(SUM(runtime_s), 0.0) as total_runtime_s,
                COALESCE(SUM(stock_energy_j), 0.0) as total_stock_energy_j,
                COALESCE(SUM(optimized_energy_j), 0.0) as total_optimized_energy_j,
                COALESCE(SUM(saved_energy_j), 0.0) as total_saved_energy_j,
                COALESCE(AVG(saved_pct), 0.0) as avg_saved_pct
            FROM savings_ledger
            """
        )
        row = cur.fetchone()
        sessions = row["sessions_count"] if row else 0
        runtime_s = row["total_runtime_s"] if row else 0.0
        stock_j = row["total_stock_energy_j"] if row else 0.0
        opt_j = row["total_optimized_energy_j"] if row else 0.0
        saved_j = row["total_saved_energy_j"] if row else 0.0
        avg_pct = row["avg_saved_pct"] if row else 0.0

        avg_watts_saved = (saved_j / runtime_s) if runtime_s > 0 else 0.0
        total_saved_wh = saved_j / 3600.0
        total_saved_kwh = total_saved_wh / 1000.0

        # Equivalents:
        # Typical laptop battery ~60Wh, nominal total system power ~15W
        battery_extension_minutes = (total_saved_wh / 15.0) * 60.0
        # Average grid carbon intensity ~390g CO2 / kWh
        co2_saved_grams = total_saved_kwh * 390.0

        return {
            "sessions_count": sessions,
            "total_runtime_s": round(runtime_s, 2),
            "total_stock_energy_j": round(stock_j, 1),
            "total_optimized_energy_j": round(opt_j, 1),
            "total_saved_energy_j": round(saved_j, 1),
            "total_saved_energy_wh": round(total_saved_wh, 2),
            "total_saved_energy_kwh": round(total_saved_kwh, 4),
            "avg_saved_pct": round(avg_pct, 1),
            "avg_watts_saved": round(avg_watts_saved, 2),
            "battery_extension_minutes": round(battery_extension_minutes, 1),
            "co2_saved_grams": round(co2_saved_grams, 2),
        }

    def get_savings_ledger(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """Retrieve recent savings entries from the ledger."""
        cur = self.conn.execute(
            """
            SELECT * FROM savings_ledger
            ORDER BY timestamp_iso DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        results = []
        for row in cur.fetchall():
            d = dict(row)
            d["metadata"] = json.loads(d["metadata_json"]) if d.get("metadata_json") else {}
            results.append(d)
        return results

    def reset_savings_ledger(self) -> int:
        """Clear all entries in the savings ledger."""
        with self.conn:
            cur = self.conn.execute("DELETE FROM savings_ledger")
            return cur.rowcount

    def export_savings_ledger(self) -> list[dict[str, Any]]:
        """Return all savings records for audit or download."""
        cur = self.conn.execute(
            "SELECT * FROM savings_ledger ORDER BY timestamp_iso DESC, id DESC"
        )
        results = []
        for row in cur.fetchall():
            d = dict(row)
            d["metadata"] = json.loads(d["metadata_json"]) if d.get("metadata_json") else {}
            results.append(d)
        return results

    def seed_demo_savings_if_empty(self) -> None:
        """Seed realistic demo savings entries if ledger is empty."""
        cur = self.conn.execute("SELECT COUNT(*) as cnt FROM savings_ledger")
        if cur.fetchone()["cnt"] > 0:
            return
        demo_entries = [
            {
                "session_id": "burst_1",
                "source": "watch",
                "workload_name": "gcc_build",
                "app_name": "Code Builder",
                "target_pid": 14205,
                "objective": "efficiency",
                "runtime_s": 42.5,
                "stock_energy_j": 1381.2,
                "optimized_energy_j": 566.3,
                "saved_energy_j": 814.9,
                "saved_pct": 59.0,
                "stock_avg_power_w": 32.5,
                "optimized_avg_power_w": 13.3,
                "saved_avg_power_w": 19.2,
                "timestamp_iso": "2026-09-10T11:15:20Z",
                "metadata": {"cores": 12, "freq_ghz": 3.8},
            },
            {
                "session_id": "burst_2",
                "source": "watch",
                "workload_name": "rust_cargo",
                "app_name": "Cargo Watch",
                "target_pid": 18392,
                "objective": "deadline",
                "runtime_s": 88.0,
                "stock_energy_j": 2860.0,
                "optimized_energy_j": 1716.0,
                "saved_energy_j": 1144.0,
                "saved_pct": 40.0,
                "stock_avg_power_w": 32.5,
                "optimized_avg_power_w": 19.5,
                "saved_avg_power_w": 13.0,
                "timestamp_iso": "2026-09-10T12:04:10Z",
                "metadata": {"cores": 8, "freq_ghz": 3.8, "budget_s": 95.0},
            },
            {
                "session_id": "burst_3",
                "source": "validation",
                "workload_name": "clean_build",
                "app_name": "Build Harness",
                "target_pid": 21094,
                "objective": "efficiency",
                "runtime_s": 15.2,
                "stock_energy_j": 494.0,
                "optimized_energy_j": 202.5,
                "saved_energy_j": 291.5,
                "saved_pct": 59.0,
                "stock_avg_power_w": 32.5,
                "optimized_avg_power_w": 13.3,
                "saved_avg_power_w": 19.2,
                "timestamp_iso": "2026-09-10T13:45:00Z",
                "metadata": {"cores": 12, "freq_ghz": 3.4},
            },
        ]
        for e in demo_entries:
            self.record_savings_entry(e, enforce_opt_in=False)

