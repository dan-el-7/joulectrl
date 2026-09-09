"""tests/unit/test_clean_build.py — Tests for zstd clean-build workload plugin."""

import os
import tempfile
import unittest
from pathlib import Path

from workloads.base import RunContext
from workloads.clean_build import CleanBuildWorkload


class TestCleanBuildWorkload(unittest.TestCase):
    def test_clean_build_properties(self):
        wl = CleanBuildWorkload(source_pin="v1.5.6", target="zstd")
        self.assertEqual(wl.name, "clean_build")
        self.assertIn("v1.5.6", wl.description)
        self.assertIn("zstd", wl.description)

    def test_clean_state_preparation(self):
        with tempfile.TemporaryDirectory(prefix="joulectrl_cb_test_") as tmpdir:
            # Create dummy source files and dummy old build artifacts
            src_dir = Path(tmpdir)
            (src_dir / "main.c").write_text("int main() { return 0; }")
            (src_dir / "header.h").write_text("#define TEST 1")
            (src_dir / "old_object.o").write_text("dummy binary content")
            (src_dir / "zstd.exe").write_text("old binary")

            wl = CleanBuildWorkload(source_dir=str(src_dir), target="zstd")
            ctx = RunContext(working_dir=tmpdir, worker_count=4)

            wl.prepare(ctx)

            # Check that old build artifacts were cleaned
            self.assertFalse((src_dir / "old_object.o").exists())
            self.assertFalse((src_dir / "zstd.exe").exists())
            # Check source files still exist
            self.assertTrue((src_dir / "main.c").exists())
            self.assertTrue((src_dir / "header.h").exists())
            self.assertTrue(ctx.artifacts.get("clean_state_verified"))
            self.assertGreaterEqual(ctx.artifacts.get("warmed_bytes", 0), 0)

    def test_command_and_environment(self):
        wl = CleanBuildWorkload(source_dir="/opt/zstd", target="zstd", cflags="-O3")
        cmd = wl.command(workers=8)
        self.assertIsInstance(cmd, list)
        self.assertEqual(cmd[0], "make")
        self.assertIn("-j8", cmd)
        self.assertIn("CFLAGS=-O3", cmd)
        self.assertIn("zstd", cmd)

        env = wl.environment(workers=8)
        self.assertEqual(env["CCACHE_DISABLE"], "1")
        self.assertEqual(env["SCCACHE_DISABLE"], "1")
        self.assertEqual(env["MAKEFLAGS"], "-j8")

    def test_verify_checks(self):
        with tempfile.TemporaryDirectory(prefix="joulectrl_cb_verify_") as tmpdir:
            src_dir = Path(tmpdir)
            wl = CleanBuildWorkload(source_dir=str(src_dir), target="zstd")
            ctx = RunContext(working_dir=tmpdir)

            # Failure when exit code != 0
            ctx.exit_code = 1
            self.assertFalse(wl.verify(ctx))

            # Failure when binary does not exist
            ctx.exit_code = 0
            self.assertFalse(wl.verify(ctx))

    def test_fingerprint(self):
        wl = CleanBuildWorkload(source_pin="v1.5.6", target="zstd", cflags="-O2")
        fp = wl.fingerprint()
        self.assertEqual(fp["workload"], "clean_build")
        self.assertEqual(fp["project"], "zstd")
        self.assertEqual(fp["source_pin"], "v1.5.6")
        self.assertEqual(fp["target"], "zstd")
        self.assertEqual(fp["compiler_caching_disabled"], True)


if __name__ == "__main__":
    unittest.main()
