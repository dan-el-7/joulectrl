"""explain/facts.py — Structured fact extraction for joulectrl explanations.

Follows Grounding Rules from PLAN §10:
- Deterministic extraction from Profile, Selection, and Validation results.
- Canonical percentages and metrics are computed in code.
- Excludes source code, raw logs, sensitive paths, and machine identifiers.
"""

from __future__ import annotations

from typing import Any, Optional

from core.models import CapabilityReport, Profile, Selection, ValidationPair


def extract_explanation_facts(
    selection: Selection,
    profile: Optional[Profile] = None,
    validation_pairs: Optional[list[ValidationPair]] = None,
    capability_report: Optional[CapabilityReport] = None,
) -> dict[str, Any]:
    """Extract structured, grounded facts for explanation generation."""
    facts: dict[str, Any] = {
        "experiment_id": selection.experiment_id,
        "objective_mode": selection.objective_mode,
        "status": selection.status,
        "status_message": selection.status_message,
        "deadline_s": selection.deadline_s,
        "margin": selection.margin,
        "energy_target_pct": selection.energy_target_pct,
        "perf_floor_pct": selection.perf_floor_pct,
        "preference_outcome_state": selection.preference_outcome_state,
        "energy_reduction_pct": selection.energy_reduction_pct,
        "runtime_increase_pct": selection.runtime_increase_pct,
    }

    # Selected configuration details
    if selection.selected_configuration is not None:
        cfg = selection.selected_configuration
        facts["selected_config"] = {
            "id": cfg.id,
            "layout": cfg.layout,
            "worker_count": cfg.worker_count,
            "freq_cap_khz": cfg.freq_cap_khz,
            "boost": cfg.boost,
            "median_energy_j": selection.selected_median_energy_j,
            "median_runtime_s": selection.selected_median_runtime_s,
            "guarded_runtime_s": selection.selected_guarded_runtime_s,
        }
    else:
        facts["selected_config"] = None

    # Baseline configuration details
    facts["baseline_config"] = {
        "id": selection.baseline_config_id,
        "median_energy_j": selection.baseline_median_energy_j,
        "median_runtime_s": selection.baseline_median_runtime_s,
    }

    # Profile analysis: find lowest-energy overall and fastest overall
    if profile is not None and profile.configurations:
        usable = [c for c in profile.configurations.values() if c.profile_is_usable and c.median_energy_j is not None]
        if usable:
            lowest_energy_cfg = min(usable, key=lambda c: c.median_energy_j if c.median_energy_j is not None else float("inf"))
            fastest_cfg = min(usable, key=lambda c: c.median_runtime_s)
            
            facts["lowest_energy_overall"] = {
                "id": lowest_energy_cfg.config_id,
                "layout": lowest_energy_cfg.configuration.layout,
                "median_energy_j": lowest_energy_cfg.median_energy_j,
                "median_runtime_s": lowest_energy_cfg.median_runtime_s,
                "guarded_runtime_s": lowest_energy_cfg.guarded_runtime_s,
                "was_selected": (selection.selected_config_id == lowest_energy_cfg.config_id),
                "exceeded_budget": (
                    selection.deadline_s is not None
                    and lowest_energy_cfg.guarded_runtime_s > selection.deadline_s
                ),
            }
            facts["fastest_overall"] = {
                "id": fastest_cfg.config_id,
                "layout": fastest_cfg.configuration.layout,
                "median_energy_j": fastest_cfg.median_energy_j,
                "median_runtime_s": fastest_cfg.median_runtime_s,
            }

        # Rejected configurations summary
        rejections = []
        for cid, c in profile.configurations.items():
            if cid == selection.selected_config_id:
                continue
            reason = c.rejection_reason or ""
            if selection.deadline_s is not None and c.guarded_runtime_s > selection.deadline_s:
                reason = f"Guarded runtime {c.guarded_runtime_s:.1f}s exceeded budget {selection.deadline_s:.1f}s"
            elif selection.selected_median_energy_j is not None and c.median_energy_j is not None:
                if c.median_energy_j > selection.selected_median_energy_j:
                    reason = f"Energy {c.median_energy_j:.1f}J higher than selected {selection.selected_median_energy_j:.1f}J"
            if reason:
                rejections.append({"config_id": cid, "reason": reason})
        facts["rejections"] = rejections
    else:
        facts["lowest_energy_overall"] = None
        facts["fastest_overall"] = None
        facts["rejections"] = []

    # Validation pairs summary
    if validation_pairs:
        total = len(validation_pairs)
        met_budget_count = sum(1 for p in validation_pairs if p.met_budget)
        all_succeeded = all(p.both_succeeded for p in validation_pairs)
        facts["validation"] = {
            "total_pairs": total,
            "met_budget_count": met_budget_count,
            "all_succeeded": all_succeeded,
            "validation_passed": (met_budget_count == total and all_succeeded),
        }
    else:
        facts["validation"] = None

    # Hardware context (narrowed per grounding rule)
    if capability_report is not None:
        facts["hardware"] = {
            "cpu_model": capability_report.cpu_model,
            "energy_backend": capability_report.energy_backend_name,
            "control_tier": capability_report.control_tier,
        }
    else:
        facts["hardware"] = None

    return facts
