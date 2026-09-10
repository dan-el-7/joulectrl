"""core/optimizer.py — Deterministic optimizer for joulectrl (Agent B owned).

Core principles (from PLAN Section 6):
1. Entirely deterministic — no ML model is used to calculate recommendations.
2. Selection is exact over candidate measured configurations.
3. Guarded runtime rule: T_guard = max(samples) * (1 + margin) (default margin 5%).
4. Objectives:
   - Deadline mode (default): argmin E_c subject to T_guard,c <= D.
   - Preference mode (AGENTS.md Section 6c): min energy meeting both energy_target_pct
     and perf_floor_pct; honest closest fallbacks if not both met.
   - Frontier mode: Pareto non-dominated configurations.
5. Edge states:
   - no_feasible_point
   - baseline_already_optimal
   - within_noise
   - profile_unusable / invalid
"""

from __future__ import annotations

from statistics import median
from typing import Any, Optional

from core.models import ConfigSummary, Configuration, Profile, Selection, utc_now_iso


def compute_guarded_runtime(runtime_samples: list[float], margin: float = 0.05) -> float:
    """Compute guarded runtime estimate with empirical headroom margin.
    
    Formula from PLAN Section 6:
        T_guard = max(runtime_samples) * (1 + margin)
    """
    if not runtime_samples:
        return 0.0
    return max(runtime_samples) * (1.0 + margin)


def compute_pareto_frontier(configs: list[ConfigSummary]) -> list[ConfigSummary]:
    """Compute Pareto non-dominated configurations.
    
    Configuration A dominates B if:
    - E_A <= E_B and T_A <= T_B
    - and (E_A < E_B or T_A < T_B)
    where E is median energy and T is median runtime.
    
    Returns:
        List of non-dominated ConfigSummary objects sorted by median_runtime_s ascending.
    """
    usable = [
        c for c in configs 
        if c.profile_is_usable and c.median_energy_j is not None and c.median_runtime_s > 0
    ]
    if not usable:
        return []

    non_dominated: list[ConfigSummary] = []
    for c in usable:
        dominated = False
        for other in usable:
            if other.config_id == c.config_id:
                continue
            assert other.median_energy_j is not None
            assert c.median_energy_j is not None
            if (other.median_energy_j <= c.median_energy_j and 
                other.median_runtime_s <= c.median_runtime_s and 
                (other.median_energy_j < c.median_energy_j or other.median_runtime_s < c.median_runtime_s)):
                dominated = True
                break
        if not dominated:
            non_dominated.append(c)

    # Sort by runtime ascending
    non_dominated.sort(key=lambda x: (x.median_runtime_s, x.median_energy_j if x.median_energy_j is not None else 0.0))
    return non_dominated


def select_deadline(
    configs: list[ConfigSummary],
    deadline_s: float,
    baseline_config_id: Optional[str] = None,
    margin: float = 0.05,
    experiment_id: str = "",
    task_duration_s: Optional[float] = None,
) -> Selection:
    """Deterministic selection under a runtime deadline.
    
    Rule:
    - Feasible: profile_is_usable and T_guard <= deadline_s and median_energy_j is not None
    - Winner: argmin (median_energy, T_guard, config_id)

    When task_duration_s is provided (> 0) and baseline runtime is known:
    - Extrapolates candidate guarded runtime: T_guard,proj = task_duration_s * (T_guard,c / T_base)
    - Enforces deadline feasibility: T_guard,proj <= deadline_s
    - Extrapolates projected task runtime: T_proj = task_duration_s * (T_c / T_base)
    - Extrapolates projected package energy: E_proj = E_c * (task_duration_s / T_base)
    """
    baseline: Optional[ConfigSummary] = None
    if baseline_config_id:
        for c in configs:
            if c.config_id == baseline_config_id:
                baseline = c
                break
    if not baseline and configs:
        baseline = next((c for c in configs if c.is_baseline), configs[0])

    # Baseline metrics
    base_energy = baseline.median_energy_j if baseline and baseline.median_energy_j is not None else None
    base_runtime = baseline.median_runtime_s if baseline and baseline.median_runtime_s > 0 else None

    # Determine if workload duration extrapolation is active
    extrapolate = (
        task_duration_s is not None
        and task_duration_s > 0
        and base_runtime is not None
        and base_runtime > 0
    )

    # Check candidate feasibility and decorate summaries
    feasible: list[ConfigSummary] = []
    candidate_summaries: list[dict[str, Any]] = []

    for c in configs:
        raw_dict = c.to_dict()
        if not c.profile_is_usable or c.median_energy_j is None or not c.runtime_samples:
            raw_dict["is_feasible"] = False
            candidate_summaries.append(raw_dict)
            continue

        guarded = compute_guarded_runtime(c.runtime_samples, margin)

        if extrapolate:
            slowdown_median = c.median_runtime_s / base_runtime
            slowdown_guarded = guarded / base_runtime

            proj_runtime = task_duration_s * slowdown_median
            proj_guarded = task_duration_s * slowdown_guarded
            proj_energy = (
                c.median_energy_j * (task_duration_s / base_runtime)
                if c.median_energy_j is not None
                else None
            )

            is_feasible = proj_guarded <= deadline_s
            raw_dict["projected_runtime_s"] = proj_runtime
            raw_dict["projected_guarded_runtime_s"] = proj_guarded
            raw_dict["projected_energy_j"] = proj_energy
            raw_dict["is_feasible"] = is_feasible

            if is_feasible:
                feasible.append(c)
        else:
            is_feasible = guarded <= deadline_s
            raw_dict["is_feasible"] = is_feasible
            if is_feasible:
                feasible.append(c)

        candidate_summaries.append(raw_dict)

    frontier = compute_pareto_frontier(configs)
    frontier_ids = [c.config_id for c in frontier]

    # Edge state: No feasible point meets deadline
    if not feasible:
        if extrapolate:
            fastest_guarded_proj = min(
                (task_duration_s * (compute_guarded_runtime(c.runtime_samples, margin) / base_runtime))
                for c in configs if c.profile_is_usable and c.runtime_samples
            ) if any(c.profile_is_usable and c.runtime_samples for c in configs) else 0.0
            msg = (
                f"No configuration can complete the {task_duration_s:.1f}s task within the "
                f"deadline ({deadline_s:.1f}s) with margin ({margin * 100:.1f}%). "
                f"Fastest configuration requires {fastest_guarded_proj:.1f}s."
            )
        else:
            msg = f"No measured configuration meets the deadline ({deadline_s:.2f}s) with margin ({margin * 100:.1f}%)."

        return Selection(
            experiment_id=experiment_id,
            objective_mode="deadline",
            status="no_feasible_point",
            status_message=msg,
            deadline_s=deadline_s,
            margin=margin,
            task_duration_s=task_duration_s if extrapolate else None,
            baseline_config_id=baseline_config_id,
            baseline_median_energy_j=base_energy,
            baseline_median_runtime_s=base_runtime,
            frontier_config_ids=frontier_ids,
            candidate_summaries=candidate_summaries,
            created_at_iso=utc_now_iso(),
        )

    # Deterministic tie-breaking: median energy, then guarded runtime, then config_id
    winner = min(
        feasible,
        key=lambda c: (
            c.median_energy_j if c.median_energy_j is not None else float("inf"),
            compute_guarded_runtime(c.runtime_samples, margin),
            c.config_id,
        ),
    )

    winner_guarded = compute_guarded_runtime(winner.runtime_samples, margin)
    assert winner.median_energy_j is not None

    winner_proj_runtime = None
    winner_proj_guarded = None
    winner_proj_energy = None
    if extrapolate:
        winner_proj_runtime = task_duration_s * (winner.median_runtime_s / base_runtime)
        winner_proj_guarded = task_duration_s * (winner_guarded / base_runtime)
        winner_proj_energy = winner.median_energy_j * (task_duration_s / base_runtime)

    # Comparisons vs baseline
    energy_reduction_pct: Optional[float] = None
    runtime_increase_pct: Optional[float] = None
    if base_energy is not None and base_energy > 0:
        energy_reduction_pct = 100.0 * (1.0 - winner.median_energy_j / base_energy)
    if base_runtime is not None and base_runtime > 0:
        runtime_increase_pct = 100.0 * (winner.median_runtime_s / base_runtime - 1.0)

    # Edge state: baseline is already optimal
    if baseline and winner.config_id == baseline.config_id:
        status = "baseline_already_optimal"
        status_message = "Baseline configuration is already the lowest-energy feasible point."
    # Edge state: within measurement variation / noise
    elif baseline and base_energy is not None and abs(base_energy - winner.median_energy_j) < 1e-4:
        status = "within_noise"
        status_message = "Selected result is within observed measurement variation of baseline."
    else:
        status = "selected"
        status_message = "Lowest-energy measured configuration meeting the empirical runtime rule"

    return Selection(
        experiment_id=experiment_id,
        objective_mode="deadline",
        status=status,
        status_message=status_message,
        selected_config_id=winner.config_id,
        selected_configuration=winner.configuration,
        selected_median_energy_j=winner.median_energy_j,
        selected_guarded_runtime_s=winner_guarded,
        selected_median_runtime_s=winner.median_runtime_s,
        baseline_config_id=baseline_config_id,
        baseline_median_energy_j=base_energy,
        baseline_median_runtime_s=base_runtime,
        energy_reduction_pct=energy_reduction_pct,
        runtime_increase_pct=runtime_increase_pct,
        deadline_s=deadline_s,
        margin=margin,
        task_duration_s=task_duration_s if extrapolate else None,
        projected_runtime_s=winner_proj_runtime,
        projected_guarded_runtime_s=winner_proj_guarded,
        projected_energy_j=winner_proj_energy,
        frontier_config_ids=frontier_ids,
        candidate_summaries=candidate_summaries,
        created_at_iso=utc_now_iso(),
    )


def select_preference(
    configs: list[ConfigSummary],
    energy_target_pct: float,
    perf_floor_pct: float,
    baseline_config_id: str,
    margin: float = 0.05,
    experiment_id: str = "",
) -> Selection:
    """Deterministic selection under user preference targets (AGENTS.md Section 6c).
    
    Targets relative to measured baseline:
    - energy_target_pct: e.g. 70.0 means <= 70% of baseline median package energy
    - perf_floor_pct: e.g. 90.0 means speed >= 90% of baseline (guarded runtime <= baseline / 0.90)
    
    Honesty rules:
    - When both are met: pick lowest-energy point meeting both on guarded runtime.
    - When nothing meets both: NEVER silently relax; report closest honest outcomes:
      best meeting perf floor + its energy miss, and best meeting energy target + its runtime miss.
    """
    baseline: Optional[ConfigSummary] = None
    for c in configs:
        if c.config_id == baseline_config_id:
            baseline = c
            break

    frontier = compute_pareto_frontier(configs)
    frontier_ids = [c.config_id for c in frontier]
    candidate_summaries = [c.to_dict() for c in configs]

    if not baseline or baseline.median_energy_j is None or baseline.median_runtime_s <= 0:
        return Selection(
            experiment_id=experiment_id,
            objective_mode="preference",
            status="profile_unusable",
            status_message="Baseline configuration has missing energy or invalid runtime.",
            energy_target_pct=energy_target_pct,
            perf_floor_pct=perf_floor_pct,
            preference_outcome_state="none_feasible",
            frontier_config_ids=frontier_ids,
            candidate_summaries=candidate_summaries,
            created_at_iso=utc_now_iso(),
        )

    base_energy = baseline.median_energy_j
    base_runtime = baseline.median_runtime_s

    # Threshold values
    max_energy = base_energy * (energy_target_pct / 100.0)
    # Speed >= perf_floor_pct / 100 means runtime <= baseline_runtime / (perf_floor_pct / 100)
    max_runtime = base_runtime / (perf_floor_pct / 100.0)

    usable = [
        c for c in configs 
        if c.profile_is_usable and c.median_energy_j is not None and c.runtime_samples
    ]

    both_met: list[ConfigSummary] = []
    met_perf: list[ConfigSummary] = []
    met_energy: list[ConfigSummary] = []

    for c in usable:
        guarded_t = compute_guarded_runtime(c.runtime_samples, margin)
        assert c.median_energy_j is not None
        e_ok = c.median_energy_j <= max_energy
        p_ok = guarded_t <= max_runtime
        if e_ok and p_ok:
            both_met.append(c)
        if p_ok:
            met_perf.append(c)
        if e_ok:
            met_energy.append(c)

    if both_met:
        # Both targets met! Pick minimum median energy, tie-break guarded runtime, then config_id
        winner = min(
            both_met,
            key=lambda c: (
                c.median_energy_j if c.median_energy_j is not None else float("inf"),
                compute_guarded_runtime(c.runtime_samples, margin),
                c.config_id,
            ),
        )
        winner_guarded = compute_guarded_runtime(winner.runtime_samples, margin)
        assert winner.median_energy_j is not None
        energy_red_pct = 100.0 * (1.0 - winner.median_energy_j / base_energy)
        runtime_inc_pct = 100.0 * (winner.median_runtime_s / base_runtime - 1.0)

        return Selection(
            experiment_id=experiment_id,
            objective_mode="preference",
            status="selected",
            status_message="Lowest-energy measured configuration meeting your preference rule",
            selected_config_id=winner.config_id,
            selected_configuration=winner.configuration,
            selected_median_energy_j=winner.median_energy_j,
            selected_guarded_runtime_s=winner_guarded,
            selected_median_runtime_s=winner.median_runtime_s,
            baseline_config_id=baseline_config_id,
            baseline_median_energy_j=base_energy,
            baseline_median_runtime_s=base_runtime,
            energy_reduction_pct=energy_red_pct,
            runtime_increase_pct=runtime_inc_pct,
            energy_target_pct=energy_target_pct,
            perf_floor_pct=perf_floor_pct,
            preference_outcome_state="both_met",
            perf_floor_miss_pct=0.0,
            energy_target_miss_pct=0.0,
            margin=margin,
            frontier_config_ids=frontier_ids,
            candidate_summaries=candidate_summaries,
            created_at_iso=utc_now_iso(),
        )

    # When nothing meets both: report closest honest outcomes explicitly
    closest_perf_winner: Optional[ConfigSummary] = None
    energy_miss_pct: Optional[float] = None
    if met_perf:
        # Best meeting perf floor: lowest energy among those meeting perf floor
        closest_perf_winner = min(
            met_perf,
            key=lambda c: (
                c.median_energy_j if c.median_energy_j is not None else float("inf"),
                compute_guarded_runtime(c.runtime_samples, margin),
                c.config_id,
            ),
        )
        assert closest_perf_winner.median_energy_j is not None
        # Energy miss: percentage above target energy
        energy_miss_pct = 100.0 * (closest_perf_winner.median_energy_j - max_energy) / base_energy

    closest_energy_winner: Optional[ConfigSummary] = None
    perf_miss_pct: Optional[float] = None
    if met_energy:
        # Best meeting energy target: lowest guarded runtime among those meeting energy target
        closest_energy_winner = min(
            met_energy,
            key=lambda c: (
                compute_guarded_runtime(c.runtime_samples, margin),
                c.median_energy_j if c.median_energy_j is not None else float("inf"),
                c.config_id,
            ),
        )
        w_guarded = compute_guarded_runtime(closest_energy_winner.runtime_samples, margin)
        # Perf miss: percentage runtime excess over max_runtime
        perf_miss_pct = 100.0 * (w_guarded - max_runtime) / base_runtime

    # If neither target can be met by any config
    if not closest_perf_winner and not closest_energy_winner:
        return Selection(
            experiment_id=experiment_id,
            objective_mode="preference",
            status="no_feasible_point",
            status_message="No configuration could meet either the energy target or performance floor.",
            energy_target_pct=energy_target_pct,
            perf_floor_pct=perf_floor_pct,
            preference_outcome_state="none_feasible",
            baseline_config_id=baseline_config_id,
            baseline_median_energy_j=base_energy,
            baseline_median_runtime_s=base_runtime,
            frontier_config_ids=frontier_ids,
            candidate_summaries=candidate_summaries,
            created_at_iso=utc_now_iso(),
        )

    # Prefer closest meeting perf floor (preserves execution deadline)
    winner = closest_perf_winner or closest_energy_winner
    assert winner is not None
    assert winner.median_energy_j is not None
    winner_guarded = compute_guarded_runtime(winner.runtime_samples, margin)
    outcome_state = "closest_perf_floor" if closest_perf_winner else "closest_energy_target"

    return Selection(
        experiment_id=experiment_id,
        objective_mode="preference",
        status="selected",
        status_message=f"No point met both targets; selected {outcome_state.replace('_', ' ')}.",
        selected_config_id=winner.config_id,
        selected_configuration=winner.configuration,
        selected_median_energy_j=winner.median_energy_j,
        selected_guarded_runtime_s=winner_guarded,
        selected_median_runtime_s=winner.median_runtime_s,
        baseline_config_id=baseline_config_id,
        baseline_median_energy_j=base_energy,
        baseline_median_runtime_s=base_runtime,
        energy_reduction_pct=100.0 * (1.0 - winner.median_energy_j / base_energy),
        runtime_increase_pct=100.0 * (winner.median_runtime_s / base_runtime - 1.0),
        energy_target_pct=energy_target_pct,
        perf_floor_pct=perf_floor_pct,
        preference_outcome_state=outcome_state,
        perf_floor_miss_pct=perf_miss_pct or 0.0,
        energy_target_miss_pct=energy_miss_pct or 0.0,
        margin=margin,
        frontier_config_ids=frontier_ids,
        candidate_summaries=candidate_summaries,
        created_at_iso=utc_now_iso(),
    )


def select_configuration(
    profile: Profile,
    objective_mode: str = "deadline",
    deadline_s: Optional[float] = None,
    energy_target_pct: Optional[float] = None,
    perf_floor_pct: Optional[float] = None,
    margin: float = 0.05,
    task_duration_s: Optional[float] = None,
) -> Selection:
    """Main optimizer dispatch function for an experiment Profile."""
    # Check profile validity
    if profile.validity_state == "invalidated":
        return Selection(
            experiment_id=profile.experiment_id,
            objective_mode=objective_mode,
            status="profile_unusable",
            status_message="Profile has been invalidated due to environment or machine changes.",
            created_at_iso=utc_now_iso(),
        )

    configs = list(profile.configurations.values())
    if not configs:
        return Selection(
            experiment_id=profile.experiment_id,
            objective_mode=objective_mode,
            status="no_feasible_point",
            status_message="No configurations present in profile.",
            created_at_iso=utc_now_iso(),
        )

    if objective_mode == "preference":
        e_target = energy_target_pct if energy_target_pct is not None else 70.0
        p_floor = perf_floor_pct if perf_floor_pct is not None else 90.0
        return select_preference(
            configs=configs,
            energy_target_pct=e_target,
            perf_floor_pct=p_floor,
            baseline_config_id=profile.baseline_config_id,
            margin=margin,
            experiment_id=profile.experiment_id,
        )
    elif objective_mode == "frontier":
        frontier = compute_pareto_frontier(configs)
        frontier_ids = [c.config_id for c in frontier]
        fastest = min(configs, key=lambda c: c.median_runtime_s) if configs else None
        lowest_energy = min(
            [c for c in configs if c.median_energy_j is not None],
            key=lambda c: c.median_energy_j if c.median_energy_j is not None else float("inf"),
            default=None,
        )
        return Selection(
            experiment_id=profile.experiment_id,
            objective_mode="frontier",
            status="selected" if frontier else "no_feasible_point",
            status_message="Computed Pareto non-dominated configurations frontier.",
            frontier_config_ids=frontier_ids,
            candidate_summaries=[c.to_dict() for c in configs],
            selected_config_id=lowest_energy.config_id if lowest_energy else None,
            created_at_iso=utc_now_iso(),
        )
    else:  # deadline mode (default)
        budget = deadline_s if deadline_s is not None else profile.suggested_budget_s
        if budget is None:
            # If no budget specified, default to baseline runtime
            base_cfg = profile.configurations.get(profile.baseline_config_id)
            budget = base_cfg.median_runtime_s if base_cfg and base_cfg.median_runtime_s > 0 else 60.0
        return select_deadline(
            configs=configs,
            deadline_s=budget,
            baseline_config_id=profile.baseline_config_id,
            margin=margin,
            experiment_id=profile.experiment_id,
            task_duration_s=task_duration_s,
        )


def match_frontier_by_savings_target(
    configs: list[ConfigSummary],
    target_savings_pct: float,
    baseline_config_id: Optional[str] = None,
    max_runtime_penalty_pct: Optional[float] = None,
) -> dict[str, Any]:
    """Find the Pareto frontier configuration achieving the target energy savings with minimal runtime penalty.
    
    Args:
        configs: List of ConfigSummary objects from the profile curve.
        target_savings_pct: Desired energy reduction percentage relative to baseline (e.g. 25.0%).
        baseline_config_id: Optional ID of baseline configuration.
        max_runtime_penalty_pct: Optional ceiling on allowable runtime increase (e.g. 20.0%).
        
    Returns:
        Structured dictionary with baseline metrics, selected config, empirical tradeoffs,
        and all available frontier points for visual tradeoff inspection.
    """
    if not configs:
        return {"ok": False, "error": "no_configs"}

    baseline: Optional[ConfigSummary] = None
    if baseline_config_id:
        for c in configs:
            if c.config_id == baseline_config_id:
                baseline = c
                break
    if not baseline:
        for c in configs:
            if c.is_baseline or (c.configuration and c.configuration.boost) or "stock" in c.config_id:
                baseline = c
                break
        if not baseline:
            baseline = configs[0]

    base_e = baseline.median_energy_j
    base_t = baseline.median_runtime_s

    if base_e is None or base_e <= 0 or base_t <= 0:
        return {"ok": False, "error": "invalid_baseline"}

    frontier = compute_pareto_frontier(configs)
    if not frontier:
        frontier = [c for c in configs if c.profile_is_usable and c.median_energy_j is not None and c.median_runtime_s > 0]
        frontier.sort(key=lambda x: (x.median_runtime_s, x.median_energy_j or 0.0))

    if not frontier:
        return {"ok": False, "error": "no_usable_frontier"}

    frontier_details = []
    for c in frontier:
        assert c.median_energy_j is not None
        e_saved_pct = 100.0 * (1.0 - c.median_energy_j / base_e)
        t_penalty_pct = 100.0 * (c.median_runtime_s / base_t - 1.0)
        power_w = c.median_energy_j / c.median_runtime_s if c.median_runtime_s > 0 else None
        frontier_details.append({
            "config_id": c.config_id,
            "energy_reduction_pct": round(e_saved_pct, 2),
            "runtime_increase_pct": round(t_penalty_pct, 2),
            "median_runtime_s": round(c.median_runtime_s, 4),
            "median_energy_j": round(c.median_energy_j, 2),
            "avg_power_w": round(power_w, 2) if power_w else None,
            "configuration": c.configuration.to_dict() if c.configuration else {},
            "_summary": c,
        })

    target_val = float(target_savings_pct)
    meeting = [p for p in frontier_details if p["energy_reduction_pct"] >= target_val]
    if max_runtime_penalty_pct is not None:
        meeting_with_penalty = [p for p in meeting if p["runtime_increase_pct"] <= max_runtime_penalty_pct]
        if meeting_with_penalty:
            meeting = meeting_with_penalty

    if meeting:
        winner = min(meeting, key=lambda p: (p["runtime_increase_pct"], -p["energy_reduction_pct"]))
        achieved = True
    else:
        winner = max(frontier_details, key=lambda p: (p["energy_reduction_pct"], -p["runtime_increase_pct"]))
        achieved = False

    base_power = base_e / base_t if base_t > 0 else None
    return {
        "ok": True,
        "target_savings_pct": target_val,
        "achieved_target": achieved,
        "baseline": {
            "config_id": baseline.config_id,
            "median_runtime_s": round(base_t, 4),
            "median_energy_j": round(base_e, 2),
            "avg_power_w": round(base_power, 2) if base_power else None,
            "configuration": baseline.configuration.to_dict() if baseline.configuration else {},
        },
        "selected": {
            "config_id": winner["config_id"],
            "energy_reduction_pct": winner["energy_reduction_pct"],
            "runtime_increase_pct": winner["runtime_increase_pct"],
            "median_runtime_s": winner["median_runtime_s"],
            "median_energy_j": winner["median_energy_j"],
            "avg_power_w": winner["avg_power_w"],
            "configuration": winner["configuration"],
        },
        "frontier_points": [
            {k: v for k, v in p.items() if k != "_summary"}
            for p in frontier_details
        ],
    }
