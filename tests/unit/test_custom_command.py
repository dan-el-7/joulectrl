"""tests/unit/test_custom_command.py — Tests for CustomCommandWorkload, GCC compile demo, CLI, and API."""

import os
import tempfile
import unittest
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import app
from cli.main import build_parser
from workloads.base import RunContext
from workloads.custom_command import CustomCommandWorkload, get_gcc_compile_demo_workload


class TestCustomCommandWorkload(unittest.TestCase):
    def test_custom_command_initialization(self):
        wl = CustomCommandWorkload("gcc -O3 -c main.c -o main.o")
        self.assertEqual(wl.name, "custom_command")
        self.assertEqual(wl.command(4), ["gcc", "-O3", "-c", "main.c", "-o", "main.o"])
        env = wl.environment(4)
        self.assertEqual(env["OMP_NUM_THREADS"], "4")
        self.assertEqual(env["CCACHE_DISABLE"], "1")

    def test_worker_placeholder_expansion(self):
        wl = CustomCommandWorkload(["make", "-j{workers}", "THREADS={threads}"])
        cmd = wl.command(8)
        self.assertEqual(cmd, ["make", "-j8", "THREADS=8"])

    def test_prepare_and_clean(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "output.bin"
            out_file.write_text("old data")

            prepare_marker = Path(tmpdir) / "clean_marker.txt"
            prepare_marker.write_text("to delete")

            wl = CustomCommandWorkload(
                "echo hello",
                working_dir=tmpdir,
                output_file_to_check=str(out_file),
                prepare_cmd=["rm", "-f", str(prepare_marker)],
            )
            ctx = RunContext(working_dir=tmpdir)
            wl.prepare(ctx)

            # Output file should be cleaned for fresh build
            self.assertFalse(out_file.exists())
            # Prepare command should have executed
            self.assertFalse(prepare_marker.exists())

    def test_verification(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "artifact.o"
            wl = CustomCommandWorkload(
                "echo ok",
                output_file_to_check=str(out_file),
                verify_exit_code=True,
                expected_exit_code=0,
            )

            # Case 1: non-zero exit code
            ctx1 = RunContext(working_dir=tmpdir, exit_code=1)
            self.assertFalse(wl.verify(ctx1))

            # Case 2: zero exit code, but artifact missing
            ctx2 = RunContext(working_dir=tmpdir, exit_code=0)
            self.assertFalse(wl.verify(ctx2))

            # Case 3: zero exit code, artifact exists
            out_file.write_text("binary blob")
            ctx3 = RunContext(working_dir=tmpdir, exit_code=0)
            self.assertTrue(wl.verify(ctx3))


class TestGccCompileDemo(unittest.TestCase):
    def test_get_gcc_compile_demo_kernel(self):
        wl = get_gcc_compile_demo_workload(mode="kernel")
        self.assertEqual(wl.name, "gcc_compile_demo")
        cmd = wl.command(4)
        self.assertEqual(cmd[0], "gcc")
        self.assertIn("-O3", cmd)
        self.assertIn("fixed_compute.c", " ".join(cmd))

    def test_get_gcc_compile_demo_zstd(self):
        zstd_root = Path(__file__).resolve().parents[2] / "workloads" / "build_target" / "zstd"
        if not zstd_root.exists():
            self.skipTest(
                "workloads/build_target/zstd not present (fresh clone); "
                "run scripts/setup to vendor the zstd build target"
            )
        wl = get_gcc_compile_demo_workload(mode="zstd")
        self.assertEqual(wl.name, "gcc_compile_demo")
        cmd = wl.command(6)
        self.assertEqual(cmd[0], "make")
        self.assertIn("-j6", cmd)

    def test_get_gcc_compile_demo_falls_back_without_zstd_tree(self):
        # Documented fallback: without the zstd build target, mode="zstd"
        # degrades to the single-file gcc kernel compile.
        zstd_root = Path(__file__).resolve().parents[2] / "workloads" / "build_target" / "zstd"
        if zstd_root.exists():
            self.skipTest("zstd tree present on this machine; fallback not active")
        wl = get_gcc_compile_demo_workload(mode="zstd")
        self.assertEqual(wl.name, "gcc_compile_demo")
        self.assertEqual(wl.command(6)[0], "gcc")


class TestCliMeasureCommands(unittest.TestCase):
    def setUp(self):
        self.parser = build_parser()

    def test_measure_subcommand_parsing(self):
        args = self.parser.parse_args(["measure", "make test", "--workers", "4", "--compare", "--json"])
        self.assertEqual(args.command, "measure")
        self.assertEqual(args.target_command, "make test")
        self.assertEqual(args.workers, 4)
        self.assertTrue(args.compare)
        self.assertTrue(args.json)

    def test_compile_demo_subcommand_parsing(self):
        args = self.parser.parse_args(["compile-demo", "--quick", "--compare", "--cap-khz", "1800000"])
        self.assertEqual(args.command, "compile-demo")
        self.assertTrue(args.quick)
        self.assertTrue(args.compare)
        self.assertEqual(args.cap_khz, 1800000)


@pytest.fixture
def api_client():
    return TestClient(app)


def test_api_measure_custom_command(api_client):
    res = api_client.post("/api/measure", json={
        "command": "python3 -c 'print(42)'",
        "compare_stock": False,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "run" in data
    assert data["run"]["status"] == "success"
    assert data["run"]["runtime_s"] > 0
    assert "package_energy_j" in data["run"]
    assert "avg_power_w" in data["run"]


def test_api_measure_compile_demo_kernel(api_client):
    res = api_client.post("/api/measure", json={
        "compare_stock": False,
        "mode": "kernel",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "run" in data
    assert data["run"]["status"] == "success"
    assert "fixed_compute.c" in data["command"]
    assert data["run"]["runtime_s"] > 0


def test_api_measure_compare(api_client):
    res = api_client.post("/api/measure", json={
        "command": "python3 -c 'sum(x for x in range(1000000))'",
        "compare_stock": True,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "stock" in data
    assert "optimized" in data
    assert "comparison" in data
    comp = data["comparison"]
    assert "runtime_stock_s" in comp
    assert "runtime_opt_s" in comp
    assert "energy_stock_j" in comp
    assert "avg_power_stock_w" in comp


def test_api_launch_terminal_mocked(api_client, monkeypatch):
    import shutil
    import subprocess
    from unittest.mock import MagicMock

    fake_proc = MagicMock()
    fake_proc.pid = 99999
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: fake_proc)
    monkeypatch.setattr(shutil, "which", lambda cmd: f"/usr/bin/{cmd}")

    res = api_client.post("/api/demo/launch-terminal", json={
        "mode": "kernel",
        "compare": True,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "terminal" in data
    assert data["pid"] == 99999
    assert "command" in data

