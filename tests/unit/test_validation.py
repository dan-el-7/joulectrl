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


# ---------------------------------------------------------------------------
# Execution-layout validation points (PLAN §6, Gate 3 B-item)
# ---------------------------------------------------------------------------

from core.models import CoreClassMap
from core.validation import dedupe_configurations, layout_configurations


def heterogeneous_map():
    return CoreClassMap(
        classes={"fast": [0, 2, 4, 6, 8, 10, 12, 14], "efficient": [1, 3, 5, 7, 9, 11, 13, 15]},
        layouts={"B": list(range(16)), "C": list(range(16))},
        fast_class="fast",
        efficient_class="efficient",
        is_heterogeneous=True,
    )


def test_layout_configurations_build_all_four_layouts():
    configs = {c.id: c for c in layout_configurations(heterogeneous_map())}
    assert set(configs) == {"layout_A_fast_4c", "layout_B_all_physical", "layout_C_all_logical", "layout_D_efficient_4c"}
    a = configs["layout_A_fast_4c"]
    assert a.layout == "A" and a.worker_count == 4
    assert a.cpu_affinity == [0, 2, 4, 6]
    d = configs["layout_D_efficient_4c"]
    assert d.cpu_affinity == [1, 3, 5, 7]
    b = configs["layout_B_all_physical"]
    assert b.layout == "B" and b.worker_count == 8
    c = configs["layout_C_all_logical"]
    assert c.layout == "C" and c.worker_count == 16


def test_layout_fallback_when_class_identification_unavailable():
    class_map = CoreClassMap(
        classes={"all": list(range(16))},
        layouts={"B": list(range(16)), "C": list(range(16))},
        fast_class="",
        efficient_class="",
        is_heterogeneous=False,
    )
    configs = {c.id: c for c in layout_configurations(class_map)}
    assert "layout_A_fast_4c" not in configs
    assert "layout_D_efficient_4c" not in configs
    fallback = configs["layout_A_unclassified_4c"]
    assert fallback.worker_count == 4
    assert "fallback" in fallback.metadata["description"]
    assert "class identification unavailable" in fallback.metadata["description"]


def test_dedupe_configurations_collapses_identical_resolutions():
    cfg1 = Configuration(id="a", layout="A", worker_count=4, cpu_affinity=[0, 2, 4, 6])
    cfg_dup = Configuration(id="a2", layout="A", worker_count=4, cpu_affinity=[6, 4, 2, 0])
    cfg_other = Configuration(id="b", layout="A", worker_count=4, cpu_affinity=[0, 2, 4, 8])
    result = dedupe_configurations([cfg1, cfg_dup, cfg_other])
    assert [c.id for c in result] == ["a", "b"]
