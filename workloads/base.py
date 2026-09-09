"""workloads/base.py — Workload plugin contract for joulectrl (Agent D owned).

Frozen contract per PLAN §8 and AGENTS.md §5:
Every workload plugin implements:
- prepare(run_context) -> None
- command(workers: int) -> list[str]
- environment(workers: int) -> dict[str, str]
- verify(run_context) -> bool
- fingerprint() -> dict[str, Any]

Rules:
1. Commands must be argument arrays (list[str]), never shell-interpolated strings.
2. Preparation and verification run OUTSIDE the energy/runtime measurement window.
3. Measurement brackets only the execution of command().
4. Worker count is explicitly passed to command() and environment(); work must not scale with workers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class RunContext:
    """Execution context passed to prepare() and verify().
    
    Contains runtime directories, configuration identifiers, and storage
    for run artifacts and verification logs.
    """
    working_dir: str
    run_id: str = ""
    config_id: str = ""
    worker_count: int = 1
    artifacts: dict[str, Any] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    exit_code: Optional[int] = None


class Workload(ABC):
    """Abstract base class for all joulectrl workload plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this workload plugin."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this workload measures."""
        ...

    @abstractmethod
    def prepare(self, run_context: RunContext) -> None:
        """Prepare the environment outside the measurement window.
        
        Examples:
        - Clean previous build artifacts (clean-build workload).
        - Warm filesystem cache if required.
        - Ensure input datasets / source code exist.
        """
        ...

    @abstractmethod
    def command(self, workers: int) -> list[str]:
        """Return the executable command as an argument array (never shell string).
        
        Args:
            workers: Number of worker threads/processes allocated.
        Returns:
            Argument array e.g. ["ninja", "-C", "build", "-j", str(workers)]
        """
        ...

    @abstractmethod
    def environment(self, workers: int) -> dict[str, str]:
        """Return process environment variables for command execution.
        
        Args:
            workers: Number of worker threads/processes allocated.
        Returns:
            Dictionary of environment variables e.g. {"OMP_NUM_THREADS": str(workers)}
        """
        ...

    @abstractmethod
    def verify(self, run_context: RunContext) -> bool:
        """Verify execution correctness outside the measurement window.
        
        Checks that:
        - Expected output artifact exists and is non-empty.
        - Smoke test or deterministic checksum matches expected value.
        - Exit code was 0.
        
        Returns:
            True if verification succeeded, False otherwise.
        """
        ...

    @abstractmethod
    def fingerprint(self) -> dict[str, Any]:
        """Return structured metadata identifying this workload for persistence.
        
        Must include:
        - Workload name and version.
        - Source revision / pin (commit hash, tarball SHA, or version).
        - Compiler / toolchain identifier and optimization flags.
        - Target artifact name.
        - Workload parameters (chunks, iterations, dataset size).
        """
        ...
