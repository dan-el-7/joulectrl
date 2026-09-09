"""workloads package — Workload plugin system for joulectrl."""

from workloads.base import RunContext, Workload
from workloads.clean_build import CleanBuildWorkload
from workloads.fixed_compute import FixedComputeWorkload, PRESETS
from workloads.registry import get_workload, list_workloads, register_workload

__all__ = [
    "CleanBuildWorkload",
    "FixedComputeWorkload",
    "PRESETS",
    "RunContext",
    "Workload",
    "get_workload",
    "list_workloads",
    "register_workload",
]
