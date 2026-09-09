"""tests/integration/test_workload_lifecycle.py — E2E integration tests for workloads, store, and explanations."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from core.experiment import ExperimentStateMachine
from core.models import Profile, Selection, ValidationPair, CalibrationRecord
from core.store import Store
from explain.facts import extract_explanation_facts
from explain.templates import generate_explanation
from workloads.base import RunContext
from workloads.fixed_compute import FixedComputeWorkload

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures" / "synthetic"


class TestWorkloadLifecycleIntegration(unittest.TestCase):
    def test_fixed_compute_execution_and_verification(self):
        """Test full execution of FixedComputeWorkload through process invocation."""
        with tempfile.TemporaryDirectory(prefix="joulectrl_int_fc_") as tmpdir:
            wl = FixedComputeWorkload(chunks=512, iters=20000)
            ctx = RunContext(working_dir=tmpdir, worker_count=2, run_id="int_run_1")

            # 1. Prepare outside measurement
            wl.prepare(ctx)
            self.assertIn("binary_path", ctx.artifacts)
            binary = ctx.artifacts["binary_path"]
            self.assertTrue(os.path.exists(binary))

            # 2. Run command (measured step in harness)
            cmd = wl.command(workers=2)
            env = dict(os.environ)
            env.update(wl.environment(workers=2))

            proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
            ctx.exit_code = proc.returncode
            ctx.stdout = proc.stdout
            ctx.stderr = proc.stderr

            self.assertEqual(proc.returncode, 0)
            
            # 3. Verify outside measurement
            verified = wl.verify(ctx)
            self.assertTrue(verified)
            self.assertIn("checksum", ctx.artifacts)
            self.assertTrue(ctx.artifacts["checksum"].startswith("0x"))

    def test_store_and_explanation_roundtrip(self):
        """Test storing synthetic profile & selection in SQLite store and generating explanation."""
        # 1. Load synthetic fixtures
        with open(FIXTURES_DIR / "synthetic_profile.json", "r", encoding="utf-8") as f:
            profile_data = json.load(f)
            profile = Profile.from_dict(profile_data)

        with open(FIXTURES_DIR / "synthetic_selection.json", "r", encoding="utf-8") as f:
            selection_data = json.load(f)
            selection = Selection.from_dict(selection_data)

        with open(FIXTURES_DIR / "synthetic_validation_pairs.json", "r", encoding="utf-8") as f:
            val_pairs_data = json.load(f)
            val_pairs = [ValidationPair.from_dict(p) for p in val_pairs_data]

        with open(FIXTURES_DIR / "synthetic_calibration_records.json", "r", encoding="utf-8") as f:
            calib_data = json.load(f)
            calib_records = [CalibrationRecord.from_dict(r) for r in calib_data]

        # 2. Persist in SQLite memory Store (Agent B contract)
        store = Store(":memory:")
        exp_id = profile.experiment_id

        store.create_experiment(
            experiment_id=exp_id,
            workload_name=profile.workload_name,
            objective=selection.objective_mode,
            runtime_budget_s=selection.deadline_s,
        )

        for run in profile.runs:
            store.record_run(run)

        store.save_profile(profile)
        store.save_selection(selection)
        
        for cal in calib_records:
            store.record_calibration(cal)

        # 3. Query back from store and verify
        exported = store.export_experiment(exp_id)
        self.assertIsNotNone(exported)
        self.assertEqual(exported["id"], exp_id)
        self.assertEqual(exported["profile"]["baseline_config_id"], profile.baseline_config_id)
        self.assertEqual(exported["selection"]["selected_config_id"], selection.selected_config_id)

        runs = store.get_runs(exp_id)
        self.assertEqual(len(runs), len(profile.runs))

        calibs = store.get_calibrations()
        self.assertEqual(len(calibs), len(calib_records))

        # 4. Generate grounded explanation from loaded data
        facts = extract_explanation_facts(
            selection=selection,
            profile=profile,
            validation_pairs=val_pairs,
        )
        explanation = generate_explanation(facts)

        self.assertIn("cfg_zen5c_4c_3000", explanation)
        self.assertIn("48.0s runtime rule", explanation)
        self.assertIn("44.6%", explanation)
        self.assertIn("3 of 3 validation runs finished within the budget", explanation)

    def test_state_machine_lifecycle_and_restoration(self):
        """Test full experiment state machine lifecycle through completion and restoration."""
        store = Store(":memory:")
        exp_id = "exp_lifecycle_test"
        store.create_experiment(experiment_id=exp_id, workload_name="fixed_compute")

        sm = ExperimentStateMachine(store, exp_id)
        self.assertEqual(sm.state, "IDLE")

        # Step through valid sequence: IDLE -> CHECKING -> PREPARING -> PROFILING -> PROFILE_READY
        sm.transition("CHECKING", "Capability check")
        self.assertEqual(sm.state, "CHECKING")

        sm.transition("PREPARING", "Preparing workload")
        self.assertEqual(sm.state, "PREPARING")

        sm.transition("PROFILING", "Running sweep")
        self.assertEqual(sm.state, "PROFILING")

        sm.transition("PROFILE_READY", "Profiling complete")
        self.assertEqual(sm.state, "PROFILE_READY")

        # PROFILE_READY -> SELECTED -> VALIDATING -> COMPLETE
        sm.transition("SELECTED", "Candidate picked")
        self.assertEqual(sm.state, "SELECTED")

        sm.transition("VALIDATING", "Validation starting")
        self.assertEqual(sm.state, "VALIDATING")

        sm.transition("COMPLETE", "Validation passed")
        self.assertEqual(sm.state, "COMPLETE")

        # COMPLETE -> RESTORING -> RESTORED
        sm.transition("RESTORING", "Restoring system settings")
        self.assertEqual(sm.state, "RESTORING")

        sm.transition("RESTORED", "Settings confirmed")
        self.assertEqual(sm.state, "RESTORED")

        transitions = store.get_state_transitions(exp_id)
        # NONE->IDLE + 9 transitions = 10 total
        self.assertEqual(len(transitions), 10)
        self.assertEqual(transitions[-1]["to_state"], "RESTORED")

    def test_state_machine_cancellation_flow(self):
        """Test cancellation transitions from PROFILING to CANCELLING -> RESTORING -> RESTORED."""
        store = Store(":memory:")
        exp_id = "exp_cancel_test"
        store.create_experiment(experiment_id=exp_id, workload_name="clean_build")

        sm = ExperimentStateMachine(store, exp_id)
        sm.transition("CHECKING")
        sm.transition("PREPARING")
        sm.transition("PROFILING")

        # Cancel active execution
        cancelled = sm.cancel(cancel_active_run=lambda: True)
        self.assertTrue(cancelled)
        self.assertEqual(sm.state, "CANCELLING")

        sm.transition("RESTORING", "Trigger cleanup")
        sm.transition("RESTORED", "Cleanup verified")
        self.assertEqual(sm.state, "RESTORED")


if __name__ == "__main__":
    unittest.main()
