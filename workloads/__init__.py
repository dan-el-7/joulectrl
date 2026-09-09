"""workloads package — Workload plugin system for joulectrl."""

from workloads.base import RunContext, Workload
from workloads.clean_build import CleanBuildWorkload
from workloads.fixed_compute import FixedComputeWorkload

__all__ = [
    "CleanBuildWorkload",
    "FixedComputeWorkload",
    "RunContext",
    "Workload",
]
