"""Tests for the unprivileged workload measurement harness."""

from __future__ import annotations

import os
import sys
from typing import Optional

import pytest

from core.models import Configuration
from core.runner import WorkloadRunner
from workloads.base import RunContext, Workload


class SequenceEnergy:
    name = "sequence-package-energy"

    def __init__(self, *readings: Optional[int]) -> None:
        self.readings = iter(readings)

    def read_uj(self) -> Optional[int]:
        return next(self.readings)

    def max_range_uj(self) -> int:
        return 100_000_000


class PythonWorkload(Workload):
    def __init__(self, code: str, *, verified: bool = True) -> None:
        self.code = code
        self.verified = verified
        self.prepared = False
        self.verified_context: Optional[RunContext] = None

    @property
    def name(self) -> str:
        return "python-test"

    @property
    def description(self) -> str:
        return "test workload"

    def prepare(self, run_context: RunContext) -> None:
        self.prepared = True

    def command(self, workers: int) -> list[str]:
        return [sys.executable, "-c", self.code]

    def environment(self, workers: int) -> dict[str, str]:
        return {"JOULECTRL_TEST_WORKERS": str(workers)}

    def verify(self, run_context: RunContext) -> bool:
        self.verified_context = run_context
        return self.verified and run_context.exit_code == 0

    def fingerprint(self) -> dict[str, str]:
        return {"workload": self.name, "version": "test"}


def config() -> Configuration:
    return Configuration(id="test", layout="test", worker_count=2)


def test_successful_run_measures_counter_and_verifies_output(tmp_path):
    runner = WorkloadRunner(SequenceEnergy(1_000_000, 1_001_000), working_dir=str(tmp_path))
    workload = PythonWorkload("print('ok')")

    result = runner.run(workload, "experiment-1", config(), repetition=1)

    assert workload.prepared
    assert workload.verified_context is not None
    assert result.status == "success"
    assert result.output_verified
    assert result.package_energy_j == pytest.approx(0.001)
    assert result.energy_available
    assert result.avg_power_w is not None
    assert result.metadata["workload_fingerprint"]["version"] == "test"


def test_missing_energy_is_unavailable_not_zero(tmp_path):
    runner = WorkloadRunner(SequenceEnergy(None, None), working_dir=str(tmp_path))
    result = runner.run(PythonWorkload("print('ok')"), "experiment-1", config(), repetition=1)

    assert result.status == "success"
    assert not result.energy_available
    assert result.package_energy_j is None
    assert result.package_energy_j != 0


def test_failed_verification_is_retained_as_failed_run(tmp_path):
    runner = WorkloadRunner(SequenceEnergy(1_000_000, 2_000_000), working_dir=str(tmp_path))
    result = runner.run(PythonWorkload("print('ok')", verified=False), "experiment-1", config(), repetition=1)

    assert result.status == "failed"
    assert not result.output_verified
    assert "verification" in (result.error_message or "")


def test_timeout_terminates_run_and_records_timeout(tmp_path):
    runner = WorkloadRunner(SequenceEnergy(1_000_000, 2_000_000), working_dir=str(tmp_path))
    result = runner.run(
        PythonWorkload("import time; time.sleep(10)"),
        "experiment-1", config(), repetition=1, timeout_s=0.05,
    )

    assert result.status == "timeout"
    assert not result.output_verified
    assert "timeout" in (result.error_message or "")


def test_cancel_uses_posix_process_group(monkeypatch, tmp_path):
    runner = WorkloadRunner(None, working_dir=str(tmp_path), platform="linux")

    class ActiveProcess:
        pid = 4242

        def poll(self):
            return None

    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(os, "killpg", lambda pid, sig: killed.append((pid, sig)))
    runner._active_process = ActiveProcess()  # type: ignore[assignment]

    assert runner.cancel()
    assert killed == [(4242, __import__("signal").SIGTERM)]


def test_linux_affinity_is_taskset_argument_array(tmp_path):
    runner = WorkloadRunner(None, working_dir=str(tmp_path), platform="linux")
    assert runner.command_for(["build", "--flag=value"], [0, 2]) == [
        "taskset", "--cpu-list", "0,2", "build", "--flag=value"
    ]
