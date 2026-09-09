"""tests/unit/test_contrast_workload.py — Unit tests for contrast workloads and registry."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from workloads.base import RunContext, Workload
from workloads.clean_build import CleanBuildWorkload
from workloads.fixed_compute import FixedComputeWorkload, PRESETS, REFERENCE_CHECKSUMS
from workloads.registry import get_workload, list_workloads, register_workload


class TestContrastWorkloads(unittest.TestCase):
    """Test contrast workload variations, presets, and workload registry."""

    def test_presets_definitions(self):
        """Verify all defined presets have valid structure and positive chunks/iters."""
        self.assertIn("smoke", PRESETS)
        self.assertIn("light", PRESETS)
        self.assertIn("standard", PRESETS)
        self.assertIn("heavy", PRESETS)
        self.assertIn("calibration", PRESETS)
        self.assertIn("c2_sweep", PRESETS)

        for name, p in PRESETS.items():
            self.assertGreater(p["chunks"], 0)
            self.assertGreater(p["iters"], 0)
            self.assertIn("description", p)
            self.assertIn("checksum", p)
            self.assertIn((p["chunks"], p["iters"]), REFERENCE_CHECKSUMS)

    def test_preset_initialization(self):
        """Verify FixedComputeWorkload correctly initializes from presets."""
        wl_smoke = FixedComputeWorkload(preset="smoke")
        self.assertEqual(wl_smoke.chunks, 1024)
        self.assertEqual(wl_smoke.iters, 50000)
        self.assertEqual(wl_smoke.preset, "smoke")

        fp = wl_smoke.fingerprint()
        self.assertEqual(fp["preset"], "smoke")
        self.assertEqual(fp["chunks"], 1024)
        self.assertEqual(fp["iters_per_chunk"], 50000)
        self.assertEqual(fp["expected_checksum"], "0x23e23165be5ef4b6")

        # Custom override on preset
        wl_custom = FixedComputeWorkload(preset="smoke", iters=20000)
        self.assertEqual(wl_custom.chunks, 1024)
        self.assertEqual(wl_custom.iters, 20000)

        # Invalid preset
        with self.assertRaises(ValueError):
            FixedComputeWorkload(preset="non_existent_preset")

    def test_workload_registry(self):
        """Verify central registry lookups and listing."""
        workloads = list_workloads()
        ids = [w["id"] for w in workloads]
        self.assertIn("clean_build", ids)
        self.assertIn("fixed_compute", ids)

        # Check contrasting characteristics
        cb_meta = next(w for w in workloads if w["id"] == "clean_build")
        fc_meta = next(w for w in workloads if w["id"] == "fixed_compute")

        self.assertEqual(cb_meta["category"], "compilation")
        self.assertEqual(fc_meta["category"], "cpu_bound")
        self.assertEqual(cb_meta["characteristics"]["scaling_type"], "process-parallel")
        self.assertEqual(fc_meta["characteristics"]["scaling_type"], "thread-parallel")
        self.assertEqual(cb_meta["characteristics"]["io_intensity"], "high")
        self.assertEqual(fc_meta["characteristics"]["io_intensity"], "none")

        # Factory instantiation
        wl_cb = get_workload("clean_build")
        self.assertIsInstance(wl_cb, CleanBuildWorkload)

        wl_fc = get_workload("fixed_compute", preset="smoke")
        self.assertIsInstance(wl_fc, FixedComputeWorkload)
        self.assertEqual(wl_fc.chunks, 1024)

        with self.assertRaises(KeyError):
            get_workload("invalid_workload_name")

    def test_custom_workload_registration(self):
        """Verify custom workloads can be dynamically registered."""
        class MockCustomWorkload(Workload):
            @property
            def name(self) -> str:
                return "mock_custom"
            @property
            def description(self) -> str:
                return "Mock custom workload"
            def prepare(self, run_context: RunContext) -> None:
                pass
            def command(self, workers: int) -> list[str]:
                return ["echo", str(workers)]
            def environment(self, workers: int) -> dict[str, str]:
                return {}
            def verify(self, run_context: RunContext) -> bool:
                return True
            def fingerprint(self) -> dict:
                return {"workload": "mock_custom"}

        register_workload("mock_custom", MockCustomWorkload)
        inst = get_workload("mock_custom")
        self.assertIsInstance(inst, MockCustomWorkload)
        self.assertEqual(inst.name, "mock_custom")

    def test_contrast_workload_contract_execution(self):
        """Verify both workloads adhere to the same execution and verification lifecycle."""
        temp_dir = tempfile.mkdtemp(prefix="joulectrl_contrast_test_")
        try:
            # 1. Clean build contract
            cb = CleanBuildWorkload(source_dir=temp_dir)
            ctx_cb = RunContext(working_dir=temp_dir, worker_count=4)
            cb.prepare(ctx_cb)
            cmd_cb = cb.command(workers=4)
            env_cb = cb.environment(workers=4)
            self.assertEqual(cmd_cb[0], "make")
            self.assertTrue(any(arg.startswith("-j") for arg in cmd_cb))
            self.assertEqual(env_cb["CCACHE_DISABLE"], "1")

            # 2. Fixed compute contract
            fc = FixedComputeWorkload(preset="smoke")
            ctx_fc = RunContext(
                working_dir=temp_dir,
                worker_count=2,
                exit_code=0,
                stdout=json.dumps({
                    "workload": "fixed_compute",
                    "workers": 2,
                    "chunks": 1024,
                    "iters_per_chunk": 50000,
                    "total_work_units": 51200000,
                    "checksum": "0x23e23165be5ef4b6",
                    "runtime_sec": 0.05,
                }),
            )
            self.assertTrue(fc.verify(ctx_fc))
            self.assertEqual(ctx_fc.artifacts["checksum"], "0x23e23165be5ef4b6")

            # Mismatched checksum fails verification
            ctx_fc_bad = RunContext(
                working_dir=temp_dir,
                worker_count=2,
                exit_code=0,
                stdout=json.dumps({
                    "workload": "fixed_compute",
                    "checksum": "0xdeadbeef12345678",
                }),
            )
            self.assertFalse(fc.verify(ctx_fc_bad))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
