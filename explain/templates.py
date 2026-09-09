"""explain/templates.py — Deterministic rule-based explanation generator for joulectrl.

Per PLAN §10:
"Basic explanations are the default guaranteed capability. Generate explanations
from deterministic facts. Populate numerical comparisons from the same code that
renders the dashboard."
"""

from __future__ import annotations

from typing import Any


def format_deadline_explanation(facts: dict[str, Any]) -> str:
    """Format explanation for Deadline Mode selection."""
    sel = facts.get("selected_config")
    base = facts.get("baseline_config")
    deadline_s = facts.get("deadline_s")
    e_red = facts.get("energy_reduction_pct")
    t_inc = facts.get("runtime_increase_pct")

    if not sel:
        return facts.get("status_message") or "No configuration could be selected."

    lines = [
        f"The selected configuration ({sel['id']}) had the lowest median package energy "
        f"({sel['median_energy_j']:.1f} J) among measured configurations meeting your "
        f"{deadline_s:.1f}s runtime rule (guarded runtime: {sel['guarded_runtime_s']:.1f}s, including 5% margin).",
    ]

    if base and e_red is not None and t_inc is not None:
        lines.append(
            f"Compared to the baseline ({base['id']}), it reduces package energy by "
            f"{e_red:.1f}% ({base['median_energy_j']:.1f} J → {sel['median_energy_j']:.1f} J) "
            f"with a {t_inc:.1f}% runtime increase ({base['median_runtime_s']:.1f}s → {sel['median_runtime_s']:.1f}s)."
        )

    # Lowest overall note
    lowest = facts.get("lowest_energy_overall")
    if lowest and not lowest.get("was_selected"):
        if lowest.get("exceeded_budget"):
            lines.append(
                f"The lowest-energy overall configuration ({lowest['id']} at {lowest['median_energy_j']:.1f} J) "
                f"was excluded because its guarded runtime ({lowest['guarded_runtime_s']:.1f}s) exceeded your budget."
            )

    # Validation summary note
    val = facts.get("validation")
    if val:
        total = val["total_pairs"]
        met = val["met_budget_count"]
        if val["validation_passed"]:
            lines.append(f"Fresh validation confirmed this result: {met} of {total} validation runs finished within the budget.")
        else:
            lines.append(f"Caution: Fresh validation finished within the budget in {met} of {total} runs.")

    return "\n\n".join(lines)


def format_preference_explanation(facts: dict[str, Any]) -> str:
    """Format explanation for Preference Mode (§6c)."""
    sel = facts.get("selected_config")
    base = facts.get("baseline_config")
    e_target = facts.get("energy_target_pct")
    perf_floor = facts.get("perf_floor_pct")
    state = facts.get("preference_outcome_state")
    e_red = facts.get("energy_reduction_pct")
    t_inc = facts.get("runtime_increase_pct")

    lines = [
        f"Preference Mode targets: energy ≤ {e_target:.1f}% of baseline, performance ≥ {perf_floor:.1f}% of baseline speed.",
    ]

    if state == "both_met":
        lines.append(
            f"Configuration {sel['id']} satisfies both targets, achieving a {e_red:.1f}% energy reduction "
            f"while retaining {100.0 / (1.0 + (t_inc or 0.0) / 100.0):.1f}% of baseline throughput."
        )
    elif state == "closest_perf_floor":
        lines.append(
            f"No measured configuration met both targets. Selected {sel['id']} as the closest candidate meeting the performance floor."
        )
    elif state == "closest_energy_target":
        lines.append(
            f"No measured configuration met both targets. Selected {sel['id']} as the closest candidate meeting the energy target."
        )
    else:
        lines.append(facts.get("status_message") or "No configuration satisfied the preference targets.")

    if base and sel:
        lines.append(
            f"Measured result: {sel['median_energy_j']:.1f} J (vs baseline {base['median_energy_j']:.1f} J), "
            f"runtime {sel['median_runtime_s']:.1f}s (vs baseline {base['median_runtime_s']:.1f}s)."
        )

    val = facts.get("validation")
    if val and val["validation_passed"]:
        lines.append(f"Fresh validation verified: {val['met_budget_count']} of {val['total_pairs']} pairs succeeded.")

    return "\n\n".join(lines)


def format_edge_state_explanation(facts: dict[str, Any]) -> str:
    """Format explanations for required edge states per PLAN §6 and §14."""
    status = facts.get("status")
    deadline_s = facts.get("deadline_s")

    if status == "no_feasible_point":
        return (
            f"No feasible configuration found meeting your runtime budget of {deadline_s:.1f}s. "
            f"All measured configurations exceeded the guarded runtime threshold."
        )
    elif status == "baseline_already_optimal":
        return (
            "The baseline configuration is already the lowest-energy measured configuration. "
            "Applying core affinity, frequency caps, or boost disabling did not yield lower package energy."
        )
    elif status == "within_noise":
        return (
            "The selected configuration's energy difference from the baseline is within observed "
            "measurement variation. The detected energy delta is not statistically distinct from noise."
        )
    elif status == "profile_unusable":
        return "The profiling data contains execution failures or missing energy measurements and cannot be used for selection."
    elif status == "unvalidated":
        return "Configuration selected from profile, but fresh validation runs have not yet been performed."
    else:
        return facts.get("status_message") or "Selection complete."


def generate_explanation(facts: dict[str, Any]) -> str:
    """Main entry point to generate deterministic basic explanation."""
    status = facts.get("status")
    mode = facts.get("objective_mode", "deadline")

    # Handle explicit edge states first
    if status in ("no_feasible_point", "baseline_already_optimal", "within_noise", "profile_unusable", "unvalidated"):
        return format_edge_state_explanation(facts)

    if mode == "preference":
        return format_preference_explanation(facts)
    else:
        return format_deadline_explanation(facts)
