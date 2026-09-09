"""Unprivileged workload execution harness.

The runner deliberately owns only the workload measurement bracket.  Configuration
application and restoration remain the helper's responsibility; callers invoke this
after a configuration has been applied and read back.  It never uses a shell.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

from core.models import Configuration, RunRecord
from core.store import Store
from energy.base import EnergyAccumulator, EnergyBackend, EnergyError, Reading
from workloads.base import RunContext, Workload


class WorkloadRunner:
    """Run one prepared workload and retain an honest :class:`RunRecord`.

    ``prepare`` and ``verify`` are intentionally outside the energy/runtime window.
    A missing or invalid counter sample makes energy unavailable; it never becomes
    a zero-joule result.
    """

    def __init__(
        self,
        energy_backend: Optional[EnergyBackend],
        *,
        store: Optional[Store] = None,
        working_dir: str = ".",
        clock: Callable[[], float] = time.monotonic,
        platform: Optional[str] = None,
    ) -> None:
        self.energy_backend = energy_backend
        self.store = store
        self.working_dir = str(Path(working_dir).resolve())
        self.clock = clock
        self.platform = platform or sys.platform
        self._active_process: Optional[subprocess.Popen[str]] = None
        self._active_lock = threading.Lock()
        self._cancel_requested = threading.Event()

    def command_for(self, command: list[str], affinity: list[int]) -> list[str]:
        """Return a direct argument array, applying Linux affinity when requested."""
        if not command or any(not isinstance(part, str) or not part for part in command):
            raise ValueError("workload command must be a non-empty list[str]")
        if affinity and self.platform.startswith("linux"):
            return ["taskset", "--cpu-list", ",".join(str(cpu) for cpu in affinity), *command]
        return list(command)

    def run(
        self,
        workload: Workload,
        experiment_id: str,
        configuration: Configuration,
        repetition: int,
        *,
        phase: str = "profiling",
        timeout_s: Optional[float] = None,
        run_id: Optional[str] = None,
    ) -> RunRecord:
        """Prepare, measure, execute, verify, and optionally persist one run."""
        run_id = run_id or str(uuid.uuid4())
        context = RunContext(
            working_dir=self.working_dir,
            run_id=run_id,
            config_id=configuration.id,
            worker_count=configuration.worker_count,
        )
        self._cancel_requested.clear()

        try:
            workload.prepare(context)
            command = self.command_for(workload.command(configuration.worker_count), configuration.cpu_affinity)
            environment = os.environ.copy()
            environment.update(workload.environment(configuration.worker_count))
            environment.update(context.env)
        except Exception as exc:
            return self._finish(self._failed_record(
                run_id, experiment_id, workload.name, configuration, repetition, phase,
                f"prepare failed: {exc}", context,
            ))

        start_energy_uj, start_time = self._read_energy()
        process: Optional[subprocess.Popen[str]] = None
        status = "success"
        error_message: Optional[str] = None
        try:
            process = self._launch(command, environment)
            with self._active_lock:
                self._active_process = process
            try:
                stdout, stderr = process.communicate(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                status = "timeout"
                error_message = f"workload exceeded timeout of {timeout_s}s"
                self.cancel()
                stdout, stderr = process.communicate()
            context.stdout = stdout
            context.stderr = stderr
            context.exit_code = process.returncode
            if self._cancel_requested.is_set() and status != "timeout":
                status = "cancelled"
                error_message = "run cancelled"
            elif process.returncode != 0 and status == "success":
                status = "failed"
                error_message = f"workload exited with code {process.returncode}"
        except Exception as exc:
            status = "failed"
            error_message = f"launch failed: {exc}"
        finally:
            end_energy_uj, end_time = self._read_energy()
            with self._active_lock:
                self._active_process = None

        energy_j, energy_available, energy_error = self._energy_delta(
            start_energy_uj, end_energy_uj, start_time, end_time
        )
        if status == "success":
            try:
                output_verified = bool(workload.verify(context))
            except Exception as exc:
                output_verified = False
                error_message = f"verification failed: {exc}"
            if not output_verified:
                status = "failed"
                error_message = error_message or "workload output verification failed"
        else:
            output_verified = False

        metadata = {"workload_fingerprint": workload.fingerprint()}
        if energy_error:
            metadata["energy_error"] = energy_error
        record = RunRecord(
            run_id=run_id,
            experiment_id=experiment_id,
            config_id=configuration.id,
            workload_name=workload.name,
            repetition=repetition,
            phase=phase,
            start_time_monotonic=start_time,
            end_time_monotonic=end_time,
            runtime_s=max(0.0, end_time - start_time),
            package_energy_j=energy_j,
            start_energy_uj=start_energy_uj,
            end_energy_uj=end_energy_uj,
            energy_available=energy_available,
            status=status,
            exit_code=context.exit_code,
            output_verified=output_verified,
            checksum=context.artifacts.get("checksum"),
            error_message=error_message,
            configuration=configuration,
            metadata=metadata,
        )
        return self._finish(record)

    def cancel(self) -> bool:
        """Terminate the active process group, not merely its immediate parent."""
        with self._active_lock:
            process = self._active_process
        if process is None or process.poll() is not None:
            return False
        self._cancel_requested.set()
        try:
            if self.platform.startswith("win"):
                process.terminate()
            else:
                os.killpg(process.pid, signal.SIGTERM)
            return True
        except ProcessLookupError:
            return False

    def _launch(self, command: list[str], environment: dict[str, str]) -> subprocess.Popen[str]:
        kwargs: dict[str, object] = {
            "cwd": self.working_dir,
            "env": environment,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
        }
        if self.platform.startswith("win"):
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            kwargs["start_new_session"] = True
        return subprocess.Popen(command, **kwargs)  # type: ignore[arg-type]

    def _read_energy(self) -> tuple[Optional[int], float]:
        timestamp = self.clock()
        return (self.energy_backend.read_uj() if self.energy_backend else None), timestamp

    def _energy_delta(
        self,
        start_uj: Optional[int],
        end_uj: Optional[int],
        start_time: float,
        end_time: float,
    ) -> tuple[Optional[float], bool, Optional[str]]:
        if self.energy_backend is None or start_uj is None or end_uj is None:
            return None, False, "package energy counter unavailable"
        try:
            delta = EnergyAccumulator(self.energy_backend).delta(
                Reading(start_time, start_uj), Reading(end_time, end_uj)
            )
            return delta.joules, True, None
        except EnergyError as exc:
            return None, False, str(exc)

    def _failed_record(
        self,
        run_id: str,
        experiment_id: str,
        workload_name: str,
        configuration: Configuration,
        repetition: int,
        phase: str,
        error: str,
        context: RunContext,
    ) -> RunRecord:
        return RunRecord(
            run_id=run_id,
            experiment_id=experiment_id,
            config_id=configuration.id,
            workload_name=workload_name,
            repetition=repetition,
            phase=phase,
            status="failed",
            output_verified=False,
            energy_available=False,
            error_message=error,
            configuration=configuration,
            metadata={"workload_fingerprint": {}},
        )

    def _finish(self, record: RunRecord) -> RunRecord:
        if self.store is not None:
            self.store.record_run(record)
        return record
