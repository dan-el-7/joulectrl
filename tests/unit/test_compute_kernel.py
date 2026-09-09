"""Unit tests for workloads/kernel/fixed_compute.c."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

KERNEL_SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "workloads",
    "kernel",
    "fixed_compute.c",
)


class TestComputeKernel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix="joulectrl_kernel_test_")
        cls.exe_name = "fixed_compute.exe" if sys.platform == "win32" else "fixed_compute"
        cls.exe_path = os.path.join(cls.temp_dir, cls.exe_name)

        # Check for gcc or clang
        cc = os.environ.get("CC", "gcc")
        if shutil.which(cc) is None:
            raise unittest.SkipTest(f"C compiler {cc} not found in PATH")

        # Compile kernel
        compile_cmd = [cc, "-O3", "-Wall", "-pthread", KERNEL_SRC, "-o", cls.exe_path]
        proc = subprocess.run(compile_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"Kernel compilation failed: {proc.stderr}")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_checksum_invariant_across_workers(self):
        """Verify checksum is strictly invariant across 1, 2, and 4 workers."""
        checksums = {}
        for w in (1, 2, 4):
            cmd = [self.exe_path, "-w", str(w), "-c", "256", "-i", "10000", "-j"]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(res.stdout)
            checksums[w] = data["checksum"]
            self.assertEqual(data["workers"], w)
            self.assertEqual(data["chunks"], 256)
            self.assertEqual(data["iters_per_chunk"], 10000)
            self.assertEqual(data["total_work_units"], 2560000)

        self.assertEqual(checksums[1], checksums[2])
        self.assertEqual(checksums[2], checksums[4])

    def test_quiet_mode(self):
        """Verify --quiet outputs single hex checksum line."""
        cmd = [self.exe_path, "-w", "2", "-c", "128", "-i", "5000", "-q"]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        out = res.stdout.strip()
        self.assertTrue(out.startswith("0x"))
        self.assertEqual(len(out), 18)  # 0x + 16 hex chars

    def test_known_checksum(self):
        """Verify known reference checksum for chunks=1024, iters=50000."""
        cmd = [self.exe_path, "-w", "1", "-c", "1024", "-i", "50000", "-q"]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        self.assertEqual(res.stdout.strip(), "0x23e23165be5ef4b6")


if __name__ == "__main__":
    unittest.main()
