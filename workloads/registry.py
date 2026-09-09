"""workloads/registry.py — Central registry and factory for joulectrl workloads."""

from __future__ import annotations

from typing import Any, Callable, Type
from workloads.base import Workload
from workloads.clean_build import CleanBuildWorkload
from workloads.fixed_compute import FixedComputeWorkload, PRESETS


_REGISTRY: dict[str, Callable[..., Workload]] = {
    "clean_build": CleanBuildWorkload,
    "fixed_compute": FixedComputeWorkload,
}


def register_workload(name: str, factory: Callable[..., Workload]) -> None:
    """Register a workload plugin factory under a unique name."""
    _REGISTRY[name] = factory


def get_workload(name: str, **kwargs: Any) -> Workload:
    """Instantiate a workload plugin by name with optional parameters.
    
    Args:
        name: Workload identifier (e.g. 'clean_build', 'fixed_compute')
        **kwargs: Workload-specific initialization parameters (e.g. preset='smoke')
        
    Raises:
        KeyError: If the workload name is not registered.
    """
    if name not in _REGISTRY:
        available = list(_REGISTRY.keys())
        raise KeyError(f"Unknown workload '{name}'. Available: {available}")
    return _REGISTRY[name](**kwargs)


def list_workloads() -> list[dict[str, Any]]:
    """List all registered workload plugins with descriptions, categories, and parameters."""
    return [
        {
            "id": "clean_build",
            "name": "Repeatable Clean Compilation",
            "category": "compilation",
            "description": "Multi-process C/C++ compilation with disabled compiler cache and clean state.",
            "characteristics": {
                "memory_intensity": "medium",
                "io_intensity": "high",
                "scaling_type": "process-parallel",
            },
            "parameters": {
                "target": "zstd",
                "cflags": "-O2",
                "source_pin": "v1.5.6",
                "build_tool": "make",
            },
        },
        {
            "id": "fixed_compute",
            "name": "Fixed-work Compute Benchmark",
            "category": "cpu_bound",
            "description": "Deterministic CPU-bound integer hashing kernel with invariant checksum across worker counts.",
            "characteristics": {
                "memory_intensity": "low (cache resident)",
                "io_intensity": "none",
                "scaling_type": "thread-parallel",
            },
            "presets": list(PRESETS.keys()),
            "parameters": {
                "preset": "standard",
                "chunks": 4096,
                "iters": 100000,
            },
        },
    ]
