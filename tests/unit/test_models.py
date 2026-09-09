"""Unit tests for core/models.py data contracts."""

import pytest
from core.models import (
    CalibrationRecord,
    CapabilityReport,
    ConfigSummary,
    Configuration,
    CoreClassMap,
    CpuCore,
    CpuTopology,
    Profile,
    RunRecord,
    Selection,
    ValidationPair,
)


def test_cpu_topology_and_core():
    core0 = CpuCore(
        cpu_id=0,
        physical_core_id=0,
        socket_id=0,
        smt_siblings=[0, 8],
        cpuinfo_max_freq_khz=5090910,
        cpuinfo_min_freq_khz=400000,
        cpufreq_policy_id=0,
        core_class="fast",
    )
    core1 = CpuCore(
        cpu_id=1,
        physical_core_id=1,
        socket_id=0,
        smt_siblings=[1, 9],
        cpuinfo_max_freq_khz=3506494,
        cpuinfo_min_freq_khz=400000,
        cpufreq_policy_id=1,
        core_class="efficient",
    )
    topology = CpuTopology(
        sockets=[0],
        physical_cores=2,
        logical_cpus=2,
        cpus={0: core0, 1: core1},
        smt_active=True,
    )

    d = topology.to_dict()
    assert d["physical_cores"] == 2
    assert "0" in d["cpus"]
    assert d["cpus"]["0"]["cpuinfo_max_freq_khz"] == 5090910

    restored = CpuTopology.from_dict(d)
    assert restored.physical_cores == 2
    assert restored.cpus[0].core_class == "fast"
    assert restored.cpus[1].cpuinfo_max_freq_khz == 3506494


def test_core_class_map():
    class_map = CoreClassMap(
        classes={"fast": [0, 2, 4, 6, 8, 10, 12, 14], "efficient": [1, 3, 5, 7, 9, 11, 13, 15]},
        layouts={
            "A": [0, 2, 4, 6],
            "D": [1, 3, 5, 7],
            "B": [0, 1, 2, 3, 4, 5, 6, 7],
            "C": list(range(16)),
        },
        fast_class="fast",
        efficient_class="efficient",
        is_heterogeneous=True,
    )
    d = class_map.to_dict()
    assert d["is_heterogeneous"] is True
    assert len(d["layouts"]["A"]) == 4

    restored = CoreClassMap.from_dict(d)
    assert restored.fast_class == "fast"
    assert restored.layouts["D"] == [1, 3, 5, 7]


def test_configuration():
    config = Configuration(
        id="layout_a_boost0_cap2500",
        layout="A",
        worker_count=4,
        cpu_affinity=[0, 2, 4, 6],
        freq_cap_khz=2500000,
        policy_freq_caps_khz={0: 2500000, 2: 2500000, 4: 2500000, 6: 2500000},
        boost=False,
        epp="performance",
    )
    d = config.to_dict()
    assert d["boost"] is False
    assert d["freq_cap_khz"] == 2500000

    restored = Configuration.from_dict(d)
    assert restored.id == config.id
    assert restored.cpu_affinity == [0, 2, 4, 6]
    assert restored.boost is False


def test_run_record_invariants():
    # Invariant 1: Valid run with energy
    r1 = RunRecord(
        run_id="run-1",
        experiment_id="exp-1",
        config_id="stock",
        workload_name="clean_build",
        repetition=1,
        runtime_s=10.0,
        package_energy_j=250.0,
        energy_available=True,
    )
    assert r1.avg_power_w == 25.0
    assert r1.mode == "harness"

    # Invariant 2: Never report missing energy as zero!
    # If energy is unavailable, package_energy_j must be None even if passed as a number
    r2 = RunRecord(
        run_id="run-2",
        experiment_id="exp-1",
        config_id="stock",
        workload_name="clean_build",
        repetition=2,
        runtime_s=10.0,
        package_energy_j=0.0,
        energy_available=False,
    )
    assert r2.package_energy_j is None
    assert r2.avg_power_w is None

    # Invariant 3: Watch-mode detection metadata
    r_watch = RunRecord(
        run_id="watch-run-1",
        experiment_id="watch-exp-1",
        config_id="baseline",
        workload_name="unmonitored_task",
        repetition=1,
        mode="watch",
        phase="watch",
        runtime_s=42.5,
        package_energy_j=1200.0,
        idle_baseline_w=8.5,
        idle_spread_w=0.4,
        onset_ts=100.0,
        end_ts=142.5,
        poll_interval_s=1.0,
        detection_uncertainty_s=1.0,
        watch_note="estimated via idle-return detection",
    )
    assert r_watch.mode == "watch"
    assert r_watch.idle_baseline_w == 8.5
    d = r_watch.to_dict()
    restored = RunRecord.from_dict(d)
    assert restored.mode == "watch"
    assert restored.idle_baseline_w == 8.5
    assert restored.watch_note == "estimated via idle-return detection"


def test_calibration_record():
    cal = CalibrationRecord(
        calibration_id="cal-1",
        core_class="fast",
        layout="C2",
        cpus=[0, 2, 4, 6],
        requested_control={"freq_cap_khz": 3000000, "boost": False},
        accepted_control={"freq_cap_khz": 3000000, "boost": False},
        runtime_s=5.0,
        package_energy_j=100.0,
        work_units=100000.0,
        kernel_checksum="abc123sha",
        machine_fingerprint="boot-xyz",
    )
    assert cal.throughput == 20000.0
    assert cal.avg_power_w == 20.0

    d = cal.to_dict()
    assert d["requested_control"]["boost"] is False
    assert d["accepted_control"]["freq_cap_khz"] == 3000000

    restored = CalibrationRecord.from_dict(d)
    assert restored.kernel_checksum == "abc123sha"
    assert restored.accepted_control == cal.accepted_control


def test_profile_and_config_summary():
    cfg = Configuration(id="stock", layout="baseline", worker_count=16)
    summary = ConfigSummary(
        config_id="stock",
        configuration=cfg,
        runtime_samples=[10.0, 10.2, 9.8],
        energy_samples=[500.0, 510.0, 490.0],
        median_runtime_s=10.0,
        min_runtime_s=9.8,
        max_runtime_s=10.2,
        guarded_runtime_s=10.71,
        median_energy_j=500.0,
        min_energy_j=490.0,
        max_energy_j=510.0,
        profile_is_usable=True,
        is_baseline=True,
    )
    profile = Profile(
        experiment_id="exp-100",
        workload_name="clean_build",
        baseline_config_id="stock",
        configurations={"stock": summary},
        runs=[],
        machine_fingerprint="boot-1",
        margin=0.05,
        suggested_budget_s=12.0,
    )

    d = profile.to_dict()
    assert "stock" in d["configurations"]
    assert d["suggested_budget_s"] == 12.0

    restored = Profile.from_dict(d)
    assert restored.baseline_config_id == "stock"
    assert restored.configurations["stock"].median_runtime_s == 10.0
    assert restored.configurations["stock"].guarded_runtime_s == 10.71


def test_selection_contract():
    # 1. Deadline mode
    sel_deadline = Selection(
        experiment_id="exp-1",
        objective_mode="deadline",
        status="selected",
        status_message="Lowest-energy measured configuration meeting the empirical runtime rule",
        selected_config_id="layout_a_cap_2500",
        selected_median_energy_j=350.0,
        selected_guarded_runtime_s=11.5,
        baseline_config_id="stock",
        baseline_median_energy_j=500.0,
        baseline_median_runtime_s=10.0,
        energy_reduction_pct=30.0,
        runtime_increase_pct=15.0,
        deadline_s=12.0,
        margin=0.05,
    )
    d = sel_deadline.to_dict()
    assert d["energy_reduction_pct"] == 30.0
    restored = Selection.from_dict(d)
    assert restored.selected_config_id == "layout_a_cap_2500"

    # 2. Preference mode (§6c)
    sel_pref = Selection(
        experiment_id="exp-2",
        objective_mode="preference",
        status="selected",
        status_message="Lowest-energy measured configuration meeting your preference rule",
        selected_config_id="layout_d_cap_2000",
        energy_target_pct=70.0,
        perf_floor_pct=90.0,
        preference_outcome_state="both_met",
        perf_floor_miss_pct=0.0,
        energy_target_miss_pct=0.0,
    )
    d2 = sel_pref.to_dict()
    assert d2["preference_outcome_state"] == "both_met"
    restored2 = Selection.from_dict(d2)
    assert restored2.energy_target_pct == 70.0


def test_validation_pair():
    r_base = RunRecord(
        run_id="val-base-1",
        experiment_id="exp-1",
        config_id="stock",
        workload_name="clean_build",
        repetition=1,
        runtime_s=10.0,
        package_energy_j=500.0,
    )
    r_sel = RunRecord(
        run_id="val-sel-1",
        experiment_id="exp-1",
        config_id="layout_a_cap_2500",
        workload_name="clean_build",
        repetition=1,
        runtime_s=11.0,
        package_energy_j=400.0,
    )
    pair = ValidationPair(
        pair_index=1,
        baseline_run=r_base,
        selected_run=r_sel,
        met_budget=True,
        live=False,
    )
    assert pair.both_succeeded is True
    assert pair.runtime_difference_pct == pytest.approx(10.0)
    assert pair.energy_reduction_pct == pytest.approx(20.0)

    d = pair.to_dict()
    assert d["met_budget"] is True
    restored = ValidationPair.from_dict(d)
    assert restored.pair_index == 1
    assert restored.baseline_run.runtime_s == 10.0
    assert restored.selected_run.package_energy_j == 400.0


def test_capability_report():
    topo = CpuTopology(sockets=[0], physical_cores=8, logical_cpus=16)
    cmap = CoreClassMap(classes={"zen5": [0, 2], "zen5c": [1, 3]})
    report = CapabilityReport(
        machine_fingerprint="fedora-demo-laptop-boot-uuid",
        cpu_model="AMD Ryzen AI 7 350 w/ Radeon 860M",
        topology=topo,
        classes=cmap,
        energy_backend_name="powercap_rapl",
        energy_scope="package-0",
        energy_counter_range_uj=65532610987,
        energy_requires_root=True,
        control_tier="full",
        cpufreq_driver="amd-pstate-epp",
        num_policies=16,
        supported_controls=["freq_cap", "boost", "affinity"],
        boost_path_exists=True,
        boost_required_for_caps=True,
        epp_available=False,
        epp_effective=False,
        tuned_profile="throughput-performance",
        governor="performance",
    )
    d = report.to_dict()
    assert d["boost_required_for_caps"] is True
    assert d["energy_requires_root"] is True

    restored = CapabilityReport.from_dict(d)
    assert restored.cpu_model == report.cpu_model
    assert restored.energy_counter_range_uj == 65532610987
    assert restored.classes.classes == cmap.classes
