"""tests/integration/test_runner_workload.py — Integration between Workload plugins and WorkloadRunner.

Verifies Gate 2 deliverable for Agent D:
"plugin contract implemented against B's runner."
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from core.experiment import ExperimentStateMachine
from core.models import Configuration
from core.runner import WorkloadRunner
from core.store import Store
from energy.synthetic import SyntheticEnergyBackend
from workloads.fixed_compute import FixedComputeWorkload


class DynamicEnergyBackend(SyntheticEnergyBackend):
    """Synthetic backend that advances energy counter upon reads to simulate consumption."""

    def __init__(self, step_uj: int = 50_000) -> None:
        super().__init__(initial_uj=1_000_000)
        self.step_uj = step_uj

    def read_uj(self) -> int:
        val = self._current_uj
        self._current_uj += self.step_uj
        return val


class TestRunnerWorkloadIntegration(unittest.TestCase):
    def test_runner_executes_fixed_compute_workload(self):
        """Test WorkloadRunner executing FixedComputeWorkload with verified checksum."""
        with tempfile.TemporaryDirectory(prefix="joulectrl_runner_fc_") as tmpdir:
            store = Store(":memory:")
            exp_id = "exp_runner_test"
            store.create_experiment(experiment_id=exp_id, workload_name="fixed_compute")

            energy_backend = DynamicEnergyBackend(step_uj=100_000)
            runner = WorkloadRunner(
                energy_backend=energy_backend,
                store=store,
                working_dir=tmpdir,
            )

            workload = FixedComputeWorkload(chunks=512, iters=20000)
            cfg = Configuration(id="cfg_2workers", layout="A", worker_count=2)

            record = runner.run(
                workload=workload,
                experiment_id=exp_id,
                configuration=cfg,
                repetition=1,
            )

            # Assertions on honest RunRecord
            self.assertEqual(record.status, "success")
            self.assertTrue(record.output_verified)
            self.assertIsNotNone(record.checksum)
            self.assertTrue(record.checksum.startswith("0x"))
            self.assertEqual(record.exit_code, 0)
            self.assertGreater(record.runtime_s, 0.0)
            self.assertIsNotNone(record.package_energy_j)
            self.assertGreater(record.package_energy_j, 0.0)
            self.assertEqual(record.metadata["workload_fingerprint"]["workload"], "fixed_compute")

            # Verify persisted in Store
            runs = store.get_runs(exp_id)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0].run_id, record.run_id)

    def test_experiment_state_machine_with_runner_profile_point(self):
        """Test ExperimentStateMachine.run_profile_point orchestrating runner and workload."""
        with tempfile.TemporaryDirectory(prefix="joulectrl_sm_runner_") as tmpdir:
            store = Store(":memory:")
            exp_id = "exp_sm_test"
            store.create_experiment(experiment_id=exp_id, workload_name="fixed_compute")

            sm = ExperimentStateMachine(store, exp_id)
            self.assertEqual(sm.state, "IDLE")

            energy_backend = DynamicEnergyBackend(step_uj=120_000)
            runner = WorkloadRunner(
                energy_backend=energy_backend,
                store=store,
                working_dir=tmpdir,
            )

            workload = FixedComputeWorkload(chunks=256, iters=10000)
            cfg = Configuration(id="cfg_4workers", layout="B", worker_count=4)

            # run_profile_point walks IDLE -> CHECKING -> PREPARING -> PROFILING -> PROFILE_READY
            record = sm.run_profile_point(
                runner=runner,
                workload=workload,
                configuration=cfg,
                repetition=1,
            )

            self.assertEqual(record.status, "success")
            self.assertEqual(sm.state, "PROFILE_READY")

            # Complete lifecycle to reach restoration: PROFILE_READY -> SELECTED -> VALIDATING -> COMPLETE
            sm.transition("SELECTED", "Candidate selected")
            sm.transition("VALIDATING", "Running validation")
            sm.transition("COMPLETE", "Experiment complete")

            # Verify restoration path
            restored = sm.restore(restore_settings=lambda: None)
            self.assertTrue(restored)
            self.assertEqual(sm.state, "RESTORED")

            exp = store.get_experiment(exp_id)
            self.assertEqual(exp["restoration_status"], "restored")


if __name__ == "__main__":
    unittest.main()
