"""Fresh baseline/candidate validation orchestration."""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

from core.models import Configuration, CoreClassMap, Profile, RunRecord, ValidationPair
from core.store import Store


@dataclass
class LayoutSpec:
    """One PLAN §6 execution layout: mask shape, worker count, class requirement."""

    layout_id: str
    description: str
    workers: int
    requires_class: Optional[str]  # None = whole machine


def _sibling_pairs(class_cpus: Sequence[int], count: int) -> list[int]:
    """First `count` physical cores' CPUs of a class (one entry per core, assuming
    class lists are ordered and SMT siblings share a core index)."""
    return list(class_cpus[:count])


def layout_configurations(class_map: CoreClassMap) -> list[Configuration]:
    """Build the execution layouts (PLAN §6) from the discovered class map.

    Layout A: 4 verified higher-performance physical cores, one SMT sibling each.
    Layout B: all 8 physical cores, one SMT sibling each.
    Layout C: all 16 logical CPUs.
    Layout D: all four efficient-class physical cores, one SMT sibling each.

    If class identification is unavailable (heterogeneous=False / empty classes),
    fall back to a documented four-physical-core mask, labeled accordingly.
    """
    classes = class_map.classes or {}
    fast = class_map.fast_class
    efficient = class_map.efficient_class
    fast_cpus = classes.get(fast) or []
    efficient_cpus = classes.get(efficient) or []
    heterogeneous = class_map.is_heterogeneous and fast_cpus and efficient_cpus

    configs: list[Configuration] = []
    if heterogeneous:
        configs.append(
            Configuration(
                id="layout_A_fast_4c",
                layout="A",
                cpu_affinity=_sibling_pairs(fast_cpus, 4),
                worker_count=4,
                metadata={"description": "4 fast-class physical cores, one SMT sibling each"},
            )
        )
        configs.append(
            Configuration(
                id="layout_D_efficient_4c",
                layout="D",
                cpu_affinity=_sibling_pairs(efficient_cpus, 4),
                worker_count=4,
                metadata={"description": "4 efficient-class physical cores, one SMT sibling each"},
            )
        )
    else:
        # Documented fallback: first four physical CPUs, labeled accordingly.
        physical = class_map.layouts.get("B") or sorted(
            cpu for cpus in classes.values() for cpu in cpus
        )[:4]
        configs.append(
            Configuration(
                id="layout_A_unclassified_4c",
                layout="A",
                cpu_affinity=list(physical[:4]),
                worker_count=4,
                metadata={"description": "fallback: 4 physical cores (class identification unavailable)"},
            )
        )

    layout_b = class_map.layouts.get("B")
    if layout_b:
        configs.append(
            Configuration(
                id="layout_B_all_physical",
                layout="B",
                cpu_affinity=list(layout_b),
                worker_count=8,
                metadata={"description": "all physical cores, one SMT sibling each"},
            )
        )
    layout_c = class_map.layouts.get("C")
    if layout_c:
        configs.append(
            Configuration(
                id="layout_C_all_logical",
                layout="C",
                cpu_affinity=list(layout_c),
                worker_count=16,
                metadata={"description": "all logical CPUs"},
            )
        )
    return configs


def dedupe_configurations(configs: Sequence[Configuration]) -> list[Configuration]:
    """PLAN §6: deduplicate settings that resolve identically after per-policy
    resolution (same layout shape + same effective affinity + same workers)."""
    seen: dict[tuple, int] = {}
    unique: list[Configuration] = []
    for config in configs:
        key = (
            config.layout,
            tuple(sorted(set(config.cpu_affinity or []))),
            config.worker_count,
        )
        if key in seen:
            continue
        seen[key] = 1
        unique.append(config)
    return unique


@dataclass
class ValidationReport:
    pairs: list[ValidationPair] = field(default_factory=list)
    restoration_errors: list[str] = field(default_factory=list)
    deadline_s: Optional[float] = None

    @property
    def ok(self) -> bool:
        return not self.restoration_errors and all(pair.both_succeeded for pair in self.pairs)


def validation_points(profile: Profile, config_ids: Sequence[str]) -> list[Configuration]:
    """Resolve user-selected measured points; reject unknown or unusable points."""
    if profile.validity_state != "valid":
        raise ValueError(f"profile is {profile.validity_state}, not freshly valid")
    points: list[Configuration] = []
    for config_id in config_ids:
        summary = profile.configurations.get(config_id)
        if summary is None:
            raise ValueError(f"configuration {config_id!r} is not in the measured profile")
        if not summary.profile_is_usable:
            raise ValueError(f"configuration {config_id!r} is not usable")
        points.append(summary.configuration)
    if not points:
        raise ValueError("at least one measured validation point is required")
    return points


class ValidationRunner:
    """Run fresh baseline/candidate pairs with restoration around every run."""

    def __init__(
        self,
        runner,
        workload,
        experiment_id: str,
        baseline: Configuration,
        candidates: Sequence[Configuration],
        *,
        repetitions: int = 3,
        seed: int = 0,
        store: Optional[Store] = None,
        apply_configuration: Optional[Callable[[Configuration], None]] = None,
        restore_configuration: Optional[Callable[[], None]] = None,
    ) -> None:
        if repetitions < 1:
            raise ValueError("repetitions must be positive")
        if not candidates:
            raise ValueError("at least one candidate is required")
        self.runner = runner
        self.workload = workload
        self.experiment_id = experiment_id
        self.baseline = baseline
        self.candidates = list(candidates)
        self.repetitions = repetitions
        self.seed = seed
        self.store = store
        self.apply_configuration = apply_configuration
        self.restore_configuration = restore_configuration

    def run(self, deadline_s: Optional[float] = None, timeout_s: Optional[float] = None) -> ValidationReport:
        jobs = [(candidate, repetition) for candidate in self.candidates for repetition in range(1, self.repetitions + 1)]
        random.Random(self.seed).shuffle(jobs)
        report = ValidationReport(deadline_s=deadline_s)
        for pair_index, (candidate, repetition) in enumerate(jobs, 1):
            baseline_run = self._run_one(self.baseline, repetition, report, timeout_s)
            selected_run = self._run_one(candidate, repetition, report, timeout_s)
            pair = ValidationPair(
                pair_index=pair_index,
                baseline_run=baseline_run,
                selected_run=selected_run,
                live=False,
            )
            pair.met_budget = bool(
                pair.both_succeeded
                and (deadline_s is None or selected_run.runtime_s <= deadline_s)
            )
            report.pairs.append(pair)
        if self.store is not None:
            self.store.save_validation_pairs(self.experiment_id, report.pairs)
        return report

    def _run_one(
        self,
        configuration: Configuration,
        repetition: int,
        report: ValidationReport,
        timeout_s: Optional[float],
    ) -> RunRecord:
        applied = self.apply_configuration is not None
        try:
            if self.apply_configuration is not None:
                self.apply_configuration(configuration)
            return self.runner.run(
                self.workload,
                self.experiment_id,
                configuration,
                repetition,
                phase="validation",
                timeout_s=timeout_s,
            )
        except Exception as exc:
            return RunRecord(
                run_id=str(uuid.uuid4()),
                experiment_id=self.experiment_id,
                config_id=configuration.id,
                workload_name=getattr(self.workload, "name", "unknown"),
                repetition=repetition,
                phase="validation",
                status="failed",
                output_verified=False,
                energy_available=False,
                error_message=str(exc),
                configuration=configuration,
            )
        finally:
            # Restore on every exit — even when only a restore callback was
            # supplied (apply may be absent while restoration is still owed).
            if self.restore_configuration is not None:
                try:
                    self.restore_configuration()
                except Exception as exc:
                    report.restoration_errors.append(str(exc))
