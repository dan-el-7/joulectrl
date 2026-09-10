"""workloads/custom_command.py — Workload plugin for arbitrary CLI command & compilation measurement.

Allows measuring any application, CLI command, or compiler invocation with:
- High-resolution monotonic timing.
- Hardware RAPL package energy counters (Joules & µJ).
- Average power dissipation (Watts).
- Verification of returncode and output artifacts.
"""

from __future__ import annotations

import os
import shlex
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional, Union

from workloads.base import RunContext, Workload


class CustomCommandWorkload(Workload):
    """Executes an arbitrary CLI application or compilation command under energy measurement."""

    def __init__(
        self,
        command: Union[str, list[str]],
        *,
        name: str = "custom_command",
        description: Optional[str] = None,
        working_dir: Optional[str] = None,
        env: Optional[dict[str, str]] = None,
        prepare_cmd: Optional[Union[str, list[str]]] = None,
        verify_exit_code: bool = True,
        expected_exit_code: int = 0,
        output_file_to_check: Optional[str] = None,
    ):
        if isinstance(command, str):
            self._cmd_list = shlex.split(command)
            self._raw_cmd_str = command
        else:
            self._cmd_list = list(command)
            self._raw_cmd_str = " ".join(shlex.quote(c) for c in command)

        self._name = name
        self._description = description or f"Execute custom command: {self._raw_cmd_str}"
        self._working_dir = working_dir
        self._custom_env = env or {}
        self._prepare_cmd = prepare_cmd
        self._verify_exit_code = verify_exit_code
        self._expected_exit_code = expected_exit_code
        self._output_file_to_check = output_file_to_check

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    def prepare(self, run_context: RunContext) -> None:
        if self._working_dir and not os.path.exists(self._working_dir):
            os.makedirs(self._working_dir, exist_ok=True)
        # If checking an output file, purge prior build to ensure fresh work
        if self._output_file_to_check and os.path.exists(self._output_file_to_check):
            try:
                os.remove(self._output_file_to_check)
            except OSError:
                pass
        if self._prepare_cmd:
            import subprocess
            cmd = shlex.split(self._prepare_cmd) if isinstance(self._prepare_cmd, str) else list(self._prepare_cmd)
            try:
                subprocess.run(
                    cmd,
                    cwd=self._working_dir or run_context.working_dir or ".",
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

    def command(self, workers: int) -> list[str]:
        # Expand any worker placeholders
        return [
            c.replace("{workers}", str(workers)).replace("{threads}", str(workers))
            for c in self._cmd_list
        ]

    def environment(self, workers: int) -> dict[str, str]:
        env = dict(self._custom_env)
        env["OMP_NUM_THREADS"] = str(workers)
        env["RAYON_NUM_THREADS"] = str(workers)
        env["CCACHE_DISABLE"] = "1"
        env["SCCACHE_DISABLE"] = "1"
        return env

    def verify(self, run_context: RunContext) -> bool:
        if self._verify_exit_code and run_context.exit_code != self._expected_exit_code:
            return False
        if self._output_file_to_check and not os.path.exists(self._output_file_to_check):
            return False
        return True

    def fingerprint(self) -> dict[str, Any]:
        return {
            "workload": self._name,
            "command": self._cmd_list,
            "raw_command": self._raw_cmd_str,
            "verify_exit_code": self._verify_exit_code,
            "expected_exit_code": self._expected_exit_code,
        }


def get_gcc_compile_demo_workload(
    workdir: Optional[str] = None,
    mode: str = "auto",  # "auto" | "kernel" | "zstd"
) -> Workload:
    """Build a real GCC compilation workload.

    - "kernel": Compiles workloads/kernel/fixed_compute.c with gcc -O3
    - "zstd": Compiles real multi-threaded C library with make -j{workers}
    - "auto": Compiles zstd if present, otherwise kernel
    """
    repo_root = Path(__file__).resolve().parent.parent
    c_source = repo_root / "workloads" / "kernel" / "fixed_compute.c"
    zstd_dir = repo_root / "workloads" / "build_target" / "zstd" / "lib"

    if mode == "zstd" or (mode == "auto" and zstd_dir.exists() and (zstd_dir / "Makefile").exists()):
        build_cmd = ["make", "-C", str(zstd_dir), "-j{workers}"]
        clean_cmd = ["make", "-C", str(zstd_dir), "clean"]
        return CustomCommandWorkload(
            build_cmd,
            name="gcc_compile_demo",
            description=f"Real GCC C compilation of zstd library (-j{{workers}}) in {zstd_dir}",
            working_dir=str(repo_root),
            prepare_cmd=clean_cmd,
        )

    out_dir = Path(workdir or tempfile.gettempdir())
    out_bin = str(out_dir / "gcc_demo_bin")
    build_cmd = ["gcc", "-O3", "-Wall", "-Wextra", "-pthread", str(c_source), "-o", out_bin]
    return CustomCommandWorkload(
        build_cmd,
        name="gcc_compile_demo",
        description=f"Real GCC C compilation: gcc -O3 fixed_compute.c -o {out_bin}",
        working_dir=str(repo_root),
        output_file_to_check=out_bin,
    )
