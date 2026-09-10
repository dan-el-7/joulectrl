"""Unit tests for core/optimizer.py per PLAN Section 14 specifications."""

import pytest
from core.models import ConfigSummary, Configuration, Profile
from core.optimizer import (
    compute_guarded_runtime,
    compute_pareto_frontier,
    select_configuration,
    select_deadline,
    select_preference,
)


def make_summary(
    config_id: str,
    runtimes: list[float],
    energies: list[float],
    is_usable: bool = True,
    is_baseline: bool = False,
    margin: float = 0.05,
) -> ConfigSummary:
    """Helper to construct a ConfigSummary with realistic metrics."""
    med_t = sorted(runtimes)[len(runtimes) // 2]
    med_e = sorted(energies)[len(energies) // 2] if energies else None
    guarded_t = compute_guarded_runtime(runtimes, margin)
    cfg = Configuration(id=config_id, layout="test", worker_count=4)
    return ConfigSummary(
        config_id=config_id,
        configuration=cfg,
        runtime_samples=runtimes,
        energy_samples=energies,
        median_runtime_s=med_t,
        min_runtime_s=min(runtimes),
        max_runtime_s=max(runtimes),
        guarded_runtime_s=guarded_t,
        median_energy_j=med_e,
        min_energy_j=min(energies) if energies else None,
        max_energy_j=max(energies) if energies else None,
        profile_is_usable=is_usable,
        is_baseline=is_baseline,
    )


def test_guarded_runtime_differs_from_median():
    """Test that guarded runtime uses max(samples) * (1 + margin), not median."""
    samples = [10.0, 10.2, 12.0]
    margin = 0.05
    # max is 12.0, guarded is 12.0 * 1.05 = 12.6
    guarded = compute_guarded_runtime(samples, margin=margin)
    assert guarded == pytest.approx(12.6)
    assert guarded > 10.2  # median


def test_lowest_energy_feasible_point_selected():
    """Test that the lowest-energy feasible configuration is selected."""
    # Baseline: 10s, 500J
    c_base = make_summary("cfg_base", [10.0, 10.0, 10.0], [500.0, 500.0, 500.0], is_baseline=True)
    # Config 1: 11s (guarded 11.55s), 400J
    c_1 = make_summary("cfg_1", [11.0, 11.0, 11.0], [400.0, 400.0, 400.0])
    # Config 2: 12s (guarded 12.6s), 350J
    c_2 = make_summary("cfg_2", [12.0, 12.0, 12.0], [350.0, 350.0, 350.0])

    # Deadline 13s -> both c_1 (11.55s) and c_2 (12.6s) are feasible.
    # c_2 has lower energy (350J vs 400J) -> c_2 must be selected.
    sel = select_deadline([c_base, c_1, c_2], deadline_s=13.0, baseline_config_id="cfg_base")
    assert sel.status == "selected"
    assert sel.selected_config_id == "cfg_2"
    assert sel.selected_median_energy_j == 350.0
    assert sel.energy_reduction_pct == pytest.approx(30.0)  # (1 - 350/500) * 100
    assert sel.runtime_increase_pct == pytest.approx(20.0)  # (12 - 10)/10 * 100


def test_lower_energy_but_late_point_rejected():
    """Test that a lower-energy point is rejected if its guarded runtime exceeds deadline."""
    c_base = make_summary("cfg_base", [10.0, 10.0, 10.0], [500.0, 500.0, 500.0], is_baseline=True)
    # c_fast: guarded 11.0 * 1.05 = 11.55s, 400J
    c_fast = make_summary("cfg_fast", [11.0, 11.0, 11.0], [400.0, 400.0, 400.0])
    # c_slow: guarded 14.0 * 1.05 = 14.7s, 300J (much lower energy, but late)
    c_slow = make_summary("cfg_slow", [14.0, 14.0, 14.0], [300.0, 300.0, 300.0])

    # Deadline 12.0s -> c_slow is late (14.7s > 12.0s). c_fast (11.55s) is selected.
    sel = select_deadline([c_base, c_fast, c_slow], deadline_s=12.0, baseline_config_id="cfg_base")
    assert sel.status == "selected"
    assert sel.selected_config_id == "cfg_fast"


def test_no_feasible_point():
    """Test edge state when no configuration meets the deadline."""
    c_base = make_summary("cfg_base", [10.0, 10.0, 10.0], [500.0, 500.0, 500.0], is_baseline=True)
    # Deadline 9.0s -> even baseline (guarded 10.5s) cannot meet 9.0s
    sel = select_deadline([c_base], deadline_s=9.0, baseline_config_id="cfg_base")
    assert sel.status == "no_feasible_point"
    assert sel.selected_config_id is None


def test_baseline_already_optimal():
    """Test edge state when baseline is already the lowest-energy feasible point."""
    c_base = make_summary("cfg_base", [10.0, 10.0, 10.0], [400.0, 400.0, 400.0], is_baseline=True)
    c_other = make_summary("cfg_other", [11.0, 11.0, 11.0], [450.0, 450.0, 450.0])

    sel = select_deadline([c_base, c_other], deadline_s=15.0, baseline_config_id="cfg_base")
    assert sel.status == "baseline_already_optimal"
    assert sel.selected_config_id == "cfg_base"


def test_tie_behavior_deterministic():
    """Test that tie-breaking across configurations with identical energy and runtime is deterministic."""
    c_z = make_summary("cfg_z", [10.0, 10.0, 10.0], [400.0, 400.0, 400.0])
    c_a = make_summary("cfg_a", [10.0, 10.0, 10.0], [400.0, 400.0, 400.0])
    c_m = make_summary("cfg_m", [10.0, 10.0, 10.0], [400.0, 400.0, 400.0])

    # Tie break on config_id alphabetical ("cfg_a" < "cfg_m" < "cfg_z")
    sel = select_deadline([c_z, c_m, c_a], deadline_s=15.0)
    assert sel.selected_config_id == "cfg_a"


def test_invalid_unstable_profiles_rejected():
    """Test that unusable profiles (e.g. failed runs, missing energy) are rejected."""
    c_base = make_summary("cfg_base", [10.0, 10.0, 10.0], [500.0, 500.0, 500.0], is_baseline=True)
    # c_unstable has profile_is_usable = False
    c_unstable = make_summary("cfg_unstable", [9.0, 9.0, 9.0], [300.0, 300.0, 300.0], is_usable=False)
    # c_no_energy has missing energy
    c_no_energy = make_summary("cfg_no_energy", [9.5, 9.5, 9.5], [])

    sel = select_deadline([c_base, c_unstable, c_no_energy], deadline_s=15.0, baseline_config_id="cfg_base")
    assert sel.selected_config_id == "cfg_base"


def test_frontier_dominance_correct():
    """Test calculation of Pareto non-dominated configurations."""
    # c1: 10s, 500J
    c1 = make_summary("c1", [10.0], [500.0])
    # c2: 12s, 400J (non-dominated: slower but lower energy)
    c2 = make_summary("c2", [12.0], [400.0])
    # c3: 14s, 350J (non-dominated: slower but lower energy)
    c3 = make_summary("c3", [14.0], [350.0])
    # c4: 13s, 450J (DOMINATED by c2: c2 is faster (12s < 13s) and lower energy (400J < 450J))
    c4 = make_summary("c4", [13.0], [450.0])

    frontier = compute_pareto_frontier([c1, c2, c3, c4])
    frontier_ids = [c.config_id for c in frontier]

    assert "c1" in frontier_ids
    assert "c2" in frontier_ids
    assert "c3" in frontier_ids
    assert "c4" not in frontier_ids  # dominated!


def test_preference_mode_both_met():
    """Test preference mode when both energy target and perf floor are met."""
    c_base = make_summary("cfg_base", [10.0], [1000.0], is_baseline=True)
    # Target: <= 70% energy (<= 700J) and >= 90% perf (runtime <= 10.0 / 0.90 = 11.11s)
    # c_candidate: 10.2s (guarded 10.71s <= 11.11s), 650J (<= 700J)
    c_cand = make_summary("cfg_cand", [10.2], [650.0])

    sel = select_preference(
        [c_base, c_cand],
        energy_target_pct=70.0,
        perf_floor_pct=90.0,
        baseline_config_id="cfg_base",
    )
    assert sel.status == "selected"
    assert sel.selected_config_id == "cfg_cand"
    assert sel.preference_outcome_state == "both_met"
    assert sel.energy_reduction_pct == pytest.approx(35.0)


def test_preference_mode_closest_fallback():
    """Test preference mode honesty when no point meets both targets."""
    c_base = make_summary("cfg_base", [10.0], [1000.0], is_baseline=True)
    # Target: <= 60% energy (<= 600J) and >= 95% perf (runtime <= 10.52s)
    # Point A: 10.0s (meets perf floor), but 800J (misses 600J target)
    c_a = make_summary("cfg_a", [10.0], [800.0])
    # Point B: 15.0s (misses perf floor), but 500J (meets energy target)
    c_b = make_summary("cfg_b", [15.0], [500.0])

    sel = select_preference(
        [c_base, c_a, c_b],
        energy_target_pct=60.0,
        perf_floor_pct=95.0,
        baseline_config_id="cfg_base",
    )
    # Should not crash or silently relax; must report closest honest outcome
    assert sel.status == "selected"
    assert sel.preference_outcome_state in ("closest_perf_floor", "closest_energy_target")
    assert sel.selected_config_id in ("cfg_a", "cfg_b")


def test_select_configuration_with_profile_object():
    """Test high-level dispatch with Profile dataclass."""
    c_base = make_summary("cfg_base", [10.0], [500.0], is_baseline=True)
    c_opt = make_summary("cfg_opt", [11.0], [350.0])
    profile = Profile(
        experiment_id="exp-test",
        workload_name="clean_build",
        baseline_config_id="cfg_base",
        configurations={"cfg_base": c_base, "cfg_opt": c_opt},
        margin=0.05,
        suggested_budget_s=12.0,
    )

    sel = select_configuration(profile, objective_mode="deadline", deadline_s=12.0)
    assert sel.selected_config_id == "cfg_opt"
    assert sel.energy_reduction_pct == pytest.approx(30.0)


def test_select_deadline_with_task_extrapolation_rejects_slow_config():
    """Test that a 900s task with 1200s deadline rejects a 1.4x slow config that raw benchmark wouldn't reject."""
    # Baseline: 10s benchmark, 500J
    c_base = make_summary("cfg_base", [10.0, 10.0, 10.0], [500.0, 500.0, 500.0], is_baseline=True)
    # c_fast: 11s benchmark (1.10x slowdown, guarded 11.55s), 400J
    c_fast = make_summary("cfg_fast", [11.0, 11.0, 11.0], [400.0, 400.0, 400.0])
    # c_slow: 14s benchmark (1.40x slowdown, guarded 14.70s), 300J (lowest raw power)
    c_slow = make_summary("cfg_slow", [14.0, 14.0, 14.0], [300.0, 300.0, 300.0])

    # 1. Raw deadline without task extrapolation:
    # Because 14.7s <= 1200s, c_slow erroneously wins on raw seconds
    sel_raw = select_deadline([c_base, c_fast, c_slow], deadline_s=1200.0, baseline_config_id="cfg_base")
    assert sel_raw.selected_config_id == "cfg_slow"

    # 2. Grounded task extrapolation for 900s task with 1200s deadline:
    # c_fast guarded on real task: 900 * (11.55 / 10.0) = 1039.5s <= 1200s -> FEASIBLE
    # c_slow guarded on real task: 900 * (14.70 / 10.0) = 1323.0s > 1200s -> INFEASIBLE!
    sel_ext = select_deadline(
        [c_base, c_fast, c_slow],
        deadline_s=1200.0,
        baseline_config_id="cfg_base",
        task_duration_s=900.0,
    )
    assert sel_ext.status == "selected"
    assert sel_ext.selected_config_id == "cfg_fast"
    assert sel_ext.task_duration_s == 900.0
    assert sel_ext.projected_runtime_s == pytest.approx(990.0)  # 900 * 1.10
    assert sel_ext.projected_guarded_runtime_s == pytest.approx(1039.5)  # 900 * 1.155
    assert sel_ext.projected_energy_j == pytest.approx(36000.0)  # 400 * (900 / 10)
    assert sel_ext.energy_reduction_pct == pytest.approx(20.0)

    # Check candidate summary decoration
    sums = {s["config_id"]: s for s in sel_ext.candidate_summaries}
    assert sums["cfg_slow"]["is_feasible"] is False
    assert sums["cfg_slow"]["projected_guarded_runtime_s"] == pytest.approx(1323.0)
    assert sums["cfg_fast"]["is_feasible"] is True


def test_select_deadline_with_task_extrapolation_no_feasible_point():
    """Test that when deadline is tighter than fastest config on the real task, status is no_feasible_point."""
    c_base = make_summary("cfg_base", [10.0], [500.0], is_baseline=True)
    c_slow = make_summary("cfg_slow", [12.0], [400.0])

    # 900s task: baseline guarded is 900 * 1.05 = 945s. Deadline is 920s -> none meet it.
    sel = select_deadline(
        [c_base, c_slow],
        deadline_s=920.0,
        baseline_config_id="cfg_base",
        task_duration_s=900.0,
    )
    assert sel.status == "no_feasible_point"
    assert "No configuration can complete the 900.0s task within the deadline (920.0s)" in sel.status_message
