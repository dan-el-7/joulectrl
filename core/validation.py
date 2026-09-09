"""Fresh baseline/candidate validation orchestration."""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

from core.models import Configuration, Profile, RunRecord, ValidationPair
from core.store import Store


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
            if applied and self.restore_configuration is not None:
                try:
                    self.restore_configuration()
                except Exception as exc:
                    report.restoration_errors.append(str(exc))
