"""tests/integration/test_validation_export.py — Integration tests for validation pairs, drift checking, and JSON export."""

import json
import os
import shutil
import tempfile
import unittest

from typing import Any

from core.models import Configuration, Profile, RunRecord, Selection, ValidationPair
from core.store import Store


def check_baseline_drift(
    profile_baseline_energy_j: float,
    profile_baseline_runtime_s: float,
    validation_pairs: list[ValidationPair],
    drift_threshold_pct: float = 10.0,
) -> dict[str, Any]:
    """Check for baseline measurement drift between profiling and validation.
    
    Per PLAN §14:
    Detects thermal throttling, platform power profile changes, or background load
    by comparing validation baseline samples against the profiling baseline.
    """
    baseline_runtimes = [p.baseline_run.runtime_s for p in validation_pairs if p.baseline_run.runtime_s is not None]
    baseline_energies = [p.baseline_run.package_energy_j for p in validation_pairs if p.baseline_run.package_energy_j is not None]

    if not baseline_runtimes or not baseline_energies:
        return {"drift_detected": False, "reason": "insufficient_data"}

    # Compute maximum deviation from profile baseline
    max_runtime_drift_pct = max(
        abs(rt - profile_baseline_runtime_s) / profile_baseline_runtime_s * 100.0
        for rt in baseline_runtimes
    )
    max_energy_drift_pct = max(
        abs(e - profile_baseline_energy_j) / profile_baseline_energy_j * 100.0
        for e in baseline_energies
    )

    # Inter-validation drift (between first and last validation baseline run)
    inter_runtime_drift_pct = 0.0
    if len(baseline_runtimes) >= 2:
        inter_runtime_drift_pct = abs(baseline_runtimes[-1] - baseline_runtimes[0]) / baseline_runtimes[0] * 100.0

    drift_detected = (
        max_runtime_drift_pct > drift_threshold_pct
        or max_energy_drift_pct > drift_threshold_pct
        or inter_runtime_drift_pct > drift_threshold_pct
    )

    return {
        "drift_detected": drift_detected,
        "max_runtime_drift_pct": max_runtime_drift_pct,
        "max_energy_drift_pct": max_energy_drift_pct,
        "inter_runtime_drift_pct": inter_runtime_drift_pct,
        "threshold_pct": drift_threshold_pct,
        "sample_count": len(validation_pairs),
    }


class TestValidationAndExportIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="joulectrl_val_test_")
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.store = Store(self.db_path)
        self.exp_id = "exp_val_export_001"

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_three_fresh_pairs_and_drift_check(self):
        """Test creation, drift verification, and budget compliance of 3 fresh pairs."""
        self.store.create_experiment(self.exp_id, workload_name="clean_build", runtime_budget_s=48.0)
        self.store.record_state_transition(self.exp_id, "IDLE", "PROFILING")
        self.store.record_state_transition(self.exp_id, "PROFILING", "PROFILE_READY")

        cfg_base = Configuration(id="cfg_stock_all", layout="D", worker_count=16, cpu_affinity=list(range(16)), boost=True)
        cfg_sel = Configuration(id="cfg_zen5c_4c_3000", layout="C", worker_count=4, cpu_affinity=[1, 3, 5, 7], freq_cap_khz=3000000, boost=False)

        # 3 Fresh pairs interleaved per PLAN §14
        pairs = []
        base_runs_data = [(28.2, 1570.0), (28.4, 1578.0), (28.6, 1585.0)]
        sel_runs_data = [(44.1, 872.0), (44.3, 876.0), (44.5, 879.0)]

        for i in range(3):
            b_rt, b_ej = base_runs_data[i]
            s_rt, s_ej = sel_runs_data[i]

            b_run = RunRecord(
                run_id=f"val_b_{i+1}",
                experiment_id=self.exp_id,
                config_id=cfg_base.id,
                workload_name="clean_build",
                repetition=i+1,
                phase="validation",
                runtime_s=b_rt,
                package_energy_j=b_ej,
                energy_available=True,
                status="success",
                exit_code=0,
                output_verified=True,
                configuration=cfg_base,
            )
            s_run = RunRecord(
                run_id=f"val_s_{i+1}",
                experiment_id=self.exp_id,
                config_id=cfg_sel.id,
                workload_name="clean_build",
                repetition=i+1,
                phase="validation",
                runtime_s=s_rt,
                package_energy_j=s_ej,
                energy_available=True,
                status="success",
                exit_code=0,
                output_verified=True,
                configuration=cfg_sel,
            )
            self.store.record_run(b_run)
            self.store.record_run(s_run)

            e_red = 100.0 * (1.0 - s_ej / b_ej)
            t_diff = 100.0 * (s_rt / b_rt - 1.0)
            met_budget = (s_rt <= 48.0)

            pair = ValidationPair(
                pair_index=i + 1,
                baseline_run=b_run,
                selected_run=s_run,
                runtime_difference_pct=t_diff,
                energy_reduction_pct=e_red,
                met_budget=met_budget,
                both_succeeded=True,
            )
            pairs.append(pair)

        self.assertEqual(len(pairs), 3)
        self.assertTrue(all(p.met_budget for p in pairs))
        self.assertTrue(all(p.both_succeeded for p in pairs))

        # Check drift against profiling baseline (28.5s, 1580J)
        drift = check_baseline_drift(
            profile_baseline_energy_j=1580.0,
            profile_baseline_runtime_s=28.5,
            validation_pairs=pairs,
            drift_threshold_pct=10.0,
        )
        self.assertFalse(drift["drift_detected"])
        self.assertLess(drift["max_runtime_drift_pct"], 5.0)
        self.assertLess(drift["max_energy_drift_pct"], 5.0)

        # Test intentional drift detection when drift exceeds threshold
        drift_high = check_baseline_drift(
            profile_baseline_energy_j=1200.0,  # ~30% difference
            profile_baseline_runtime_s=20.0,
            validation_pairs=pairs,
            drift_threshold_pct=10.0,
        )
        self.assertTrue(drift_high["drift_detected"])

        # Save pairs to store
        self.store.save_validation_pairs(self.exp_id, pairs)
        self.store.record_state_transition(self.exp_id, "PROFILE_READY", "VALIDATING")
        self.store.record_state_transition(self.exp_id, "VALIDATING", "COMPLETE")

    def test_export_json_verification(self):
        """Verify full experiment export produces valid, complete, auditable JSON archive."""
        self.store.create_experiment(self.exp_id, workload_name="clean_build", runtime_budget_s=48.0)
        
        cfg = Configuration(id="cfg_test", layout="A", worker_count=4, cpu_affinity=[0, 2, 4, 6])
        run = RunRecord(
            run_id="run_1",
            experiment_id=self.exp_id,
            config_id="cfg_test",
            workload_name="clean_build",
            repetition=1,
            phase="profiling",
            runtime_s=30.0,
            package_energy_j=1000.0,
            energy_available=True,
            status="success",
            exit_code=0,
            output_verified=True,
            configuration=cfg,
        )
        self.store.record_run(run)

        # Export to file
        export_path = os.path.join(self.temp_dir, "export.json")
        exported_str = self.store.export_experiment_json(self.exp_id, file_path=export_path)

        self.assertTrue(os.path.exists(export_path))
        with open(export_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Verify export structure
        self.assertEqual(data["id"], self.exp_id)
        self.assertEqual(data["workload_name"], "clean_build")
        self.assertEqual(data["runtime_budget_s"], 48.0)
        self.assertIn("runs", data)
        self.assertEqual(len(data["runs"]), 1)
        self.assertEqual(data["runs"][0]["run_id"], "run_1")
        self.assertEqual(data["runs"][0]["package_energy_j"], 1000.0)
        self.assertIn("state_transitions", data)


if __name__ == "__main__":
    unittest.main()
