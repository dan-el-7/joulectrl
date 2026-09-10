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


def test_live_engine_validation_execution(tmp_path):
    from core.events import EventBus
    from core.store import Store
    from api import store_bridge
    from api.engine import LiveEngine
    from core.models import Configuration, RunRecord
    from unittest.mock import MagicMock, patch

    bus = EventBus()
    store = Store(str(tmp_path / "test.db"))
    store.create_experiment("exp_test_val", "clean_build", "deadline", 45.0)

    cfg_base = Configuration(id="cfg_base", layout="B", worker_count=4, cpu_affinity=[0, 1, 2, 3], boost=True)
    cfg_sel = Configuration(id="cfg_sel", layout="A", worker_count=2, cpu_affinity=[0, 2], boost=False)

    overlays = {
        "exp_test_val": {
            "id": "exp_test_val",
            "state": "selected",
            "workload_id": "dummy",
            "runtime_budget_s": 45.0,
            "profile": {
                "baseline_config_id": "cfg_base",
                "configurations": {
                    "cfg_base": {"configuration": cfg_base.to_dict(), "is_baseline": True},
                    "cfg_sel": {"configuration": cfg_sel.to_dict()},
                },
            },
            "selection": {"config_id": "cfg_sel", "configuration": cfg_sel.to_dict()},
            "validation": {"status": "not_run", "pairs": []},
        }
    }

    engine = LiveEngine(bus, store_bridge, overlays=overlays, store=store)

    # Mock runner and helper
    mock_run = MagicMock()
    mock_run.side_effect = [
        RunRecord(run_id="r1", experiment_id="exp_test_val", config_id="cfg_base", workload_name="dummy", repetition=1, runtime_s=2.0, package_energy_j=100.0, status="success"),
        RunRecord(run_id="r2", experiment_id="exp_test_val", config_id="cfg_sel", workload_name="dummy", repetition=1, runtime_s=2.2, package_energy_j=70.0, status="success"),
    ]

    with patch.object(engine, "_helper") as mock_h:
        mock_helper = MagicMock()
        mock_helper.read_energy.side_effect = [
            {"ok": True, "uj": 50_000_000, "t": 0.5},
            {"ok": True, "uj": 100_000_000, "t": 1.0},
            {"ok": True, "uj": 200_000_000, "t": 3.0},
            {"ok": True, "uj": 200_000_000, "t": 3.0},
            {"ok": True, "uj": 270_000_000, "t": 5.2},
        ]
        mock_helper.begin_session.return_value = {"ok": True}
        mock_helper.apply_configuration.return_value = {"ok": True}
        mock_helper.restore.return_value = {"ok": True}
        mock_h.return_value = mock_helper

        with patch("core.runner.WorkloadRunner.run", mock_run):
            engine._run_validation("exp_test_val", repetitions=1)

    assert overlays["exp_test_val"]["state"] == "complete"
    assert overlays["exp_test_val"]["validation"]["status"] == "verified"
    assert len(overlays["exp_test_val"]["validation"]["pairs"]) == 1
    assert overlays["exp_test_val"]["validation"]["verified_savings_pct"] == 30.0


def test_configuration_from_dict_defaults_and_fallbacks():
    from core.models import Configuration

    # Missing id uses config_id or default
    cfg1 = Configuration.from_dict({"config_id": "my_cfg", "worker_count": 4})
    assert cfg1.id == "my_cfg"
    assert cfg1.worker_count == 4
    assert cfg1.layout == "baseline"

    # Completely empty dict defaults cleanly
    cfg2 = Configuration.from_dict({})
    assert cfg2.id == "config"
    assert cfg2.worker_count == 1
    assert cfg2.layout == "baseline"


def test_live_engine_validation_resolution_with_candidate_summaries(tmp_path):
    from core.events import EventBus
    from core.store import Store
    from api import store_bridge
    from api.engine import LiveEngine
    from core.models import Configuration, RunRecord
    from unittest.mock import MagicMock, patch

    bus = EventBus()
    store = Store(str(tmp_path / "test_summaries.db"))
    store.create_experiment("exp_summaries_val", "fixed_compute", "deadline", 45.0)

    cfg_cand = {"id": "cfg_resolved", "layout": "A", "worker_count": 4, "cpu_affinity": [0, 2, 4, 6], "boost": False}

    overlays = {
        "exp_summaries_val": {
            "id": "exp_summaries_val",
            "state": "selected",
            "workload_id": "dummy",
            "runtime_budget_s": 45.0,
            "profile": {
                "baseline_config_id": "cfg_base",
                "configurations": {},  # Empty configurations dict, common in stored profiles
            },
            "selection": {
                "selected_config_id": "cfg_resolved",
                "selected_configuration": cfg_cand,
                "candidates": [{"config_id": "cfg_resolved", "configuration": cfg_cand}],
            },
            "validation": {"status": "not_run", "pairs": []},
        }
    }

    engine = LiveEngine(bus, store_bridge, overlays=overlays, store=store)

    def fake_run(wl, exp_id, cfg, repetition=1, phase="validation"):
        if cfg.id == "cfg_base":
            return RunRecord(run_id="r1", experiment_id=exp_id, config_id="cfg_base", workload_name="dummy", repetition=repetition, runtime_s=2.0, package_energy_j=100.0, status="success")
        return RunRecord(run_id="r2", experiment_id=exp_id, config_id="cfg_resolved", workload_name="dummy", repetition=repetition, runtime_s=2.2, package_energy_j=70.0, status="success")

    mock_run = MagicMock(side_effect=fake_run)

    with patch.object(engine, "_helper") as mock_h:
        mock_helper = MagicMock()
        mock_helper.read_energy.side_effect = [
            {"ok": True, "uj": 50_000_000, "t": 0.5},
            {"ok": True, "uj": 100_000_000, "t": 1.0},
            {"ok": True, "uj": 200_000_000, "t": 3.0},
            {"ok": True, "uj": 200_000_000, "t": 3.0},
            {"ok": True, "uj": 270_000_000, "t": 5.2},
        ]
        mock_helper.begin_session.return_value = {"ok": True}
        mock_helper.apply_configuration.return_value = {"ok": True}
        mock_helper.restore.return_value = {"ok": True}
        mock_h.return_value = mock_helper

        with patch("core.runner.WorkloadRunner.run", mock_run):
            engine._run_validation("exp_summaries_val", repetitions=1)

    assert overlays["exp_summaries_val"]["state"] == "complete"
    assert overlays["exp_summaries_val"]["validation"]["status"] == "verified"
    assert len(overlays["exp_summaries_val"]["validation"]["pairs"]) == 1


def test_validation_uses_invariant_fixed_chunks_across_workers():
    from workloads.fixed_compute import REFERENCE_CHECKSUMS
    from workloads.registry import get_workload
    from api.engine import LiveEngine
    from unittest.mock import MagicMock, patch

    assert (65536, 200000) in REFERENCE_CHECKSUMS
    assert REFERENCE_CHECKSUMS[(65536, 200000)] == "0x4b7ca5f1275dd718"

    engine = LiveEngine(MagicMock(), MagicMock(), overlays={}, store=None)
    captured_wls = []

    def fake_run(self, workload, exp_id, cfg, repetition=1, phase="profiling", **kwargs):
        captured_wls.append(workload)
        return RunRecord(
            run_id="r", experiment_id=exp_id, config_id=cfg.id,
            workload_name=workload.name, repetition=repetition, phase=phase,
            runtime_s=1.0, package_energy_j=10.0, status="success",
        )

    runner = MagicMock()
    runner.run.side_effect = fake_run

    base_cfg = Configuration(id="cfg_base_16", layout="A", worker_count=16, cpu_affinity=list(range(16)))
    cand_cfg = Configuration(id="cfg_cand_4", layout="A", worker_count=4, cpu_affinity=[0, 2, 4, 6])

    with patch.object(engine, "_helper", side_effect=Exception("no helper")):
        engine._overlays["exp_test_fixed"] = {
            "id": "exp_test_fixed",
            "state": "complete",
            "profile": {
                "configurations": {
                    "cfg_base_16": {"configuration": base_cfg.to_dict(), "is_baseline": True},
                    "cfg_cand_4": {"configuration": cand_cfg.to_dict()},
                }
            },
            "selection": {"selected_config_id": "cfg_cand_4", "baseline_config_id": "cfg_base_16"},
        }
        with patch("core.runner.WorkloadRunner.run", fake_run):
            engine._run_validation("exp_test_fixed", repetitions=1)

    assert len(captured_wls) == 2
    # Both baseline (16w) and candidate (4w) must compute the EXACT same chunk count
    assert captured_wls[0].chunks == 65536
    assert captured_wls[1].chunks == 65536
    assert captured_wls[0].iters == 200000
    assert captured_wls[1].iters == 200000





class TestThermalCooldown:
    def test_cooldown_waits_until_below_threshold(self, monkeypatch):
        from core.validation import ValidationRunner
        temps = iter([60.0, 55.0, 48.0])
        monkeypatch.setattr(ValidationRunner, "_cpu_temp_c", staticmethod(lambda: next(temps)))
        monkeypatch.setattr("time.sleep", lambda s: None)
        vr = ValidationRunner.__new__(ValidationRunner)
        vr.cooldown_temp_c = 50.0
        vr.cooldown_max_wait_s = 20.0

        class R: metadata = {}
        vr._thermal_cooldown(R())
        assert R.metadata == {}  # cooled before deadline, no timeout flag

    def test_cooldown_times_out_gracefully(self, monkeypatch):
        from core.validation import ValidationRunner
        monkeypatch.setattr(ValidationRunner, "_cpu_temp_c", staticmethod(lambda: 90.0))
        fake = iter([0.0, 0.0, 100.0])
        monkeypatch.setattr("time.monotonic", lambda: next(fake))
        monkeypatch.setattr("time.sleep", lambda s: None)
        vr = ValidationRunner.__new__(ValidationRunner)
        vr.cooldown_temp_c = 50.0
        vr.cooldown_max_wait_s = 20.0

        class R: metadata = {}
        vr._thermal_cooldown(R())
        assert R.metadata == {"cooldown_timeout": True}

    def test_no_sensor_skips_immediately(self, monkeypatch):
        import time as _t
        from core.validation import ValidationRunner
        monkeypatch.setattr(ValidationRunner, "_cpu_temp_c", staticmethod(lambda: None))
        called = []
        monkeypatch.setattr("time.sleep", lambda s: called.append(s))
        vr = ValidationRunner.__new__(ValidationRunner)
        vr.cooldown_temp_c = 50.0
        vr.cooldown_max_wait_s = 20.0

        class R: metadata = {}
        vr._thermal_cooldown(R())
        assert called == [] and R.metadata == {}
