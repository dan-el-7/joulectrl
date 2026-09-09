"""tests/unit/test_workloads_base.py — Tests for workload plugin contract and FixedCompute."""

import tempfile
import unittest
from typing import Any

from workloads.base import RunContext, Workload
from workloads.fixed_compute import FixedComputeWorkload


class DummyWorkload(Workload):
    @property
    def name(self) -> str:
        return "dummy"

    @property
    def description(self) -> str:
        return "Dummy workload for contract testing"

    def prepare(self, run_context: RunContext) -> None:
        run_context.artifacts["prepared"] = True

    def command(self, workers: int) -> list[str]:
        return ["dummy_binary", "--threads", str(workers)]

    def environment(self, workers: int) -> dict[str, str]:
        return {"WORKERS": str(workers)}

    def verify(self, run_context: RunContext) -> bool:
        return run_context.exit_code == 0

    def fingerprint(self) -> dict[str, Any]:
        return {"workload": "dummy", "version": "0.1.0"}


class TestWorkloadContract(unittest.TestCase):
    def test_abstract_class_cannot_be_instantiated(self):
        with self.assertRaises(TypeError):
            Workload()  # type: ignore

    def test_run_context_defaults(self):
        ctx = RunContext(working_dir="/tmp/test", run_id="run-1", config_id="cfg-1", worker_count=4)
        self.assertEqual(ctx.working_dir, "/tmp/test")
        self.assertEqual(ctx.run_id, "run-1")
        self.assertEqual(ctx.config_id, "cfg-1")
        self.assertEqual(ctx.worker_count, 4)
        self.assertEqual(ctx.artifacts, {})
        self.assertIsNone(ctx.exit_code)

    def test_dummy_workload_lifecycle(self):
        wl = DummyWorkload()
        self.assertEqual(wl.name, "dummy")
        self.assertEqual(wl.description, "Dummy workload for contract testing")

        ctx = RunContext(working_dir="/tmp/dummy")
        wl.prepare(ctx)
        self.assertTrue(ctx.artifacts.get("prepared"))

        cmd = wl.command(workers=8)
        self.assertIsInstance(cmd, list)
        self.assertEqual(cmd, ["dummy_binary", "--threads", "8"])

        env = wl.environment(workers=8)
        self.assertEqual(env, {"WORKERS": "8"})

        ctx.exit_code = 0
        self.assertTrue(wl.verify(ctx))

        ctx.exit_code = 1
        self.assertFalse(wl.verify(ctx))

        fp = wl.fingerprint()
        self.assertEqual(fp["workload"], "dummy")
        self.assertEqual(fp["version"], "0.1.0")


class TestFixedComputeWorkload(unittest.TestCase):
    def test_fixed_compute_plugin(self):
        with tempfile.TemporaryDirectory(prefix="joulectrl_fc_test_") as tmpdir:
            wl = FixedComputeWorkload(chunks=1024, iters=50000)
            self.assertEqual(wl.name, "fixed_compute")

            ctx = RunContext(working_dir=tmpdir, worker_count=2)
            wl.prepare(ctx)
            self.assertIn("binary_path", ctx.artifacts)

            cmd = wl.command(workers=2)
            self.assertIsInstance(cmd, list)
            self.assertIn("-w", cmd)
            self.assertIn("2", cmd)
            self.assertIn("-c", cmd)
            self.assertIn("1024", cmd)

            env = wl.environment(workers=2)
            self.assertEqual(env, {"OMP_NUM_THREADS": "2"})

            # Test verify with expected checksum
            ctx.exit_code = 0
            ctx.stdout = '{"workload": "fixed_compute", "checksum": "0x23e23165be5ef4b6", "total_work_units": 51200000}'
            self.assertTrue(wl.verify(ctx))
            self.assertEqual(ctx.artifacts["checksum"], "0x23e23165be5ef4b6")

            # Test verify with mismatch checksum
            ctx.stdout = '{"workload": "fixed_compute", "checksum": "0xdeadbeef", "total_work_units": 51200000}'
            self.assertFalse(wl.verify(ctx))

            # Test verify with error exit code
            ctx.exit_code = 1
            self.assertFalse(wl.verify(ctx))

            fp = wl.fingerprint()
            self.assertEqual(fp["workload"], "fixed_compute")
            self.assertEqual(fp["chunks"], 1024)
            self.assertEqual(fp["iters_per_chunk"], 50000)
            self.assertEqual(fp["total_work_units"], 51200000)
            self.assertEqual(fp["expected_checksum"], "0x23e23165be5ef4b6")
            self.assertTrue(len(fp["source_sha256"]) == 64)


if __name__ == "__main__":
    unittest.main()
