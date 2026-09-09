"""Tests for randomized fresh validation pairs."""

from core.models import Configuration, RunRecord
from core.validation import ValidationRunner


class FakeRunner:
    def __init__(self):
        self.calls = []

    def run(self, workload, experiment_id, configuration, repetition, phase, timeout_s=None):
        self.calls.append((configuration.id, repetition, phase))
        runtime = 1.0 if configuration.id == "baseline" else 1.5
        return RunRecord(
            run_id=f"{configuration.id}-{repetition}", experiment_id=experiment_id,
            config_id=configuration.id, workload_name="test", repetition=repetition,
            phase=phase, runtime_s=runtime, package_energy_j=runtime * 10,
        )


def test_validation_randomizes_pairs_and_restores_every_run():
    baseline = Configuration(id="baseline", layout="all", worker_count=4)
    candidate = Configuration(id="candidate", layout="fast", worker_count=2)
    calls = []
    runner = FakeRunner()
    report = ValidationRunner(
        runner, object(), "exp", baseline, [candidate], repetitions=2, seed=7,
        apply_configuration=lambda config: calls.append(("apply", config.id)),
        restore_configuration=lambda: calls.append(("restore", "")),
    ).run(deadline_s=2.0)

    assert len(report.pairs) == 2
    assert report.ok
    assert all(pair.met_budget for pair in report.pairs)
    assert len(calls) == 8
    assert all(call[2] == "validation" for call in runner.calls)


def test_validation_marks_restore_failure_and_never_claims_ok():
    baseline = Configuration(id="baseline", layout="all", worker_count=1)
    candidate = Configuration(id="candidate", layout="fast", worker_count=1)
    report = ValidationRunner(
        FakeRunner(), object(), "exp", baseline, [candidate], repetitions=1,
        restore_configuration=lambda: (_ for _ in ()).throw(RuntimeError("restore failed")),
    ).run()
    assert report.restoration_errors
    assert not report.ok
