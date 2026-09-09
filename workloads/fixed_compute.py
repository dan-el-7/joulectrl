"""workloads/fixed_compute.py — Fixed compute CPU benchmark plugin for joulectrl."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from typing import Any, Optional

from workloads.base import RunContext, Workload

KERNEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kernel")
KERNEL_SRC = os.path.join(KERNEL_DIR, "fixed_compute.c")

# Known reference checksums
REFERENCE_CHECKSUMS = {
    (4096, 100000): "0x3a762069507139ac",
    (1024, 50000): "0x23e23165be5ef4b6",
    (2048, 50000): "0x8d10852193c21759",
    (8192, 100000): "0x38a6af54e0c98b86",
    (16384, 200000): "0xc2493c07d6b29c85",
    (32768, 200000): "0x4f59b8763583e750",
    (65536, 200000): "0x4b7ca5f1275dd718",
}

# Standard parameter presets
PRESETS: dict[str, dict[str, Any]] = {
    "smoke": {
        "chunks": 1024,
        "iters": 50000,
        "checksum": "0x23e23165be5ef4b6",
        "description": "Fast smoke-test compute (1024 chunks, 50k iters)",
    },
    "light": {
        "chunks": 2048,
        "iters": 50000,
        "checksum": "0x8d10852193c21759",
        "description": "Light compute load (2048 chunks, 50k iters)",
    },
    "standard": {
        "chunks": 4096,
        "iters": 100000,
        "checksum": "0x3a762069507139ac",
        "description": "Standard compute benchmark (4096 chunks, 100k iters)",
    },
    "heavy": {
        "chunks": 8192,
        "iters": 100000,
        "checksum": "0x38a6af54e0c98b86",
        "description": "Heavy compute load (8192 chunks, 100k iters)",
    },
    "calibration": {
        "chunks": 16384,
        "iters": 200000,
        "checksum": "0xc2493c07d6b29c85",
        "description": "Standard C1/C2 hardware calibration sweep (16384 chunks, 200k iters)",
    },
    "c2_sweep": {
        "chunks": 32768,
        "iters": 200000,
        "checksum": "0x4f59b8763583e750",
        "description": "Dense C2 parallel scaling calibration sweep (32768 chunks, 200k iters)",
    },
}


class FixedComputeWorkload(Workload):
    """Deterministic CPU-bound integer hashing kernel workload.
    
    Demonstrates workload scaling with invariant checksum and zero GIL contention.
    Supports standard presets ('smoke', 'light', 'standard', 'heavy') or custom
    (chunks, iters) parameters.
    """

    def __init__(
        self,
        preset: Optional[str] = None,
        chunks: Optional[int] = None,
        iters: Optional[int] = None,
        binary_path: Optional[str] = None,
    ):
        self.preset = preset
        if preset is not None:
            if preset not in PRESETS:
                raise ValueError(f"Unknown preset '{preset}'. Available: {list(PRESETS.keys())}")
            p_data = PRESETS[preset]
            self.chunks = chunks if chunks is not None else p_data["chunks"]
            self.iters = iters if iters is not None else p_data["iters"]
        else:
            self.chunks = chunks if chunks is not None else 4096
            self.iters = iters if iters is not None else 100000

        self._custom_binary = binary_path
        self._resolved_binary: Optional[str] = binary_path

    @property
    def name(self) -> str:
        return "fixed_compute"

    @property
    def description(self) -> str:
        return (
            f"Deterministic parallel integer compute kernel: {self.chunks} chunks, "
            f"{self.iters} iterations per chunk, invariant checksum."
        )

    def _ensure_binary(self, working_dir: str) -> str:
        if self._resolved_binary and os.path.exists(self._resolved_binary):
            return self._resolved_binary

        exe_name = "fixed_compute.exe" if sys.platform == "win32" else "fixed_compute"
        candidate = os.path.join(working_dir, exe_name)
        if os.path.exists(candidate):
            self._resolved_binary = candidate
            return candidate

        # Compile from source
        cc = os.environ.get("CC", "gcc")
        if shutil.which(cc) is None:
            raise RuntimeError(f"C compiler {cc} not found to build fixed_compute kernel")

        target = os.path.join(working_dir, exe_name)
        compile_cmd = [cc, "-O3", "-Wall", "-Wextra", "-pthread", KERNEL_SRC, "-o", target]
        res = subprocess.run(compile_cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"Failed to build fixed_compute kernel: {res.stderr}")

        self._resolved_binary = target
        return target

    def prepare(self, run_context: RunContext) -> None:
        """Ensure binary is compiled in working_dir and outputs are clean."""
        binary = self._ensure_binary(run_context.working_dir)
        run_context.artifacts["binary_path"] = binary

    def command(self, workers: int) -> list[str]:
        """Return argument array for kernel execution."""
        binary = self._resolved_binary or "fixed_compute"
        return [
            binary,
            "-w", str(workers),
            "-c", str(self.chunks),
            "-i", str(self.iters),
            "--json",
        ]

    def environment(self, workers: int) -> dict[str, str]:
        return {"OMP_NUM_THREADS": str(workers)}

    def verify(self, run_context: RunContext) -> bool:
        """Verify exit code 0 and checksum integrity."""
        if run_context.exit_code != 0:
            return False

        if not run_context.stdout:
            return False

        try:
            data = json.loads(run_context.stdout)
        except json.JSONDecodeError:
            return False

        checksum = data.get("checksum")
        if not checksum:
            return False

        run_context.artifacts["checksum"] = checksum
        run_context.artifacts["total_work_units"] = data.get("total_work_units")

        expected = REFERENCE_CHECKSUMS.get((self.chunks, self.iters))
        if expected is not None and checksum != expected:
            return False

        return True

    def fingerprint(self) -> dict[str, Any]:
        """Return workload fingerprint."""
        src_sha = ""
        if os.path.exists(KERNEL_SRC):
            with open(KERNEL_SRC, "rb") as f:
                src_sha = hashlib.sha256(f.read()).hexdigest()

        return {
            "workload": self.name,
            "version": "1.0.0",
            "source_file": "workloads/kernel/fixed_compute.c",
            "source_sha256": src_sha,
            "chunks": self.chunks,
            "iters_per_chunk": self.iters,
            "preset": self.preset,
            "total_work_units": self.chunks * self.iters,
            "compiler": os.environ.get("CC", "gcc"),
            "cflags": "-O3 -Wall -Wextra -pthread",
            "expected_checksum": REFERENCE_CHECKSUMS.get((self.chunks, self.iters)),
        }
