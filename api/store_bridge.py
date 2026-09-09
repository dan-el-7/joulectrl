"""api/store_bridge.py — Bridge between Agent B's Store (core/store.py) and the API contract.

Agent C owned. Persists fixture-backed experiments (Agent D's synthetic fixtures plus the
Gate-1 demo fixture) into Agent B's SQLite Store, and adapts the persisted model-shaped
records into the frozen API shapes documented in docs/API.md. The API never invents
measurements: everything served here round-trips through the real Store layer.
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import median
from typing import Any, Optional

from core.models import (
    CalibrationRecord,
    Profile,
    Selection,
    ValidationPair,
)
from core.store import Store

SYNTHETIC_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "synthetic"

SYNTHETIC_EXPERIMENT_ID = "exp_synthetic_clean_build_001"
DEMO_EXPERIMENT_ID = "exp_demo_clean_build"


def _load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def persist_experiment_dict(
    store: Store,
    exp: dict[str, Any],
    final_state: str = "COMPLETE",
    restoration_status: str = "restored",
) -> dict[str, Any]:
    """Persist an API-shaped experiment dict (model-shaped profile/selection/validation)
    into the Store and return the stored row.

    Run IDs are namespaced with the experiment id: the runs table keys on run_id
    alone (INSERT OR REPLACE), and fixture experiments reuse identical run ids
    across experiments, which would silently reassign runs otherwise.
    """
    store.create_experiment(
        exp["id"],
        exp.get("workload_id", "clean_build"),
        objective=exp.get("objective", "deadline"),
        runtime_budget_s=exp.get("runtime_budget_s"),
        preference=exp.get("preference"),
    )
    profile = Profile.from_dict(exp.get("profile") or {})
    for run in profile.runs:
        run.run_id = f"{exp['id']}:{run.run_id}"
        store.record_run(run)
    store.save_profile(profile)
    if exp.get("selection"):
        store.save_selection(Selection.from_dict(exp["selection"]))
    pairs = [ValidationPair.from_dict(p) for p in (exp.get("validation") or {}).get("pairs", [])]
    if pairs:
        store.save_validation_pairs(exp["id"], pairs)
    store.transition_state(exp["id"], final_state, "seeded from fixture data")
    store.update_restoration_status(exp["id"], restoration_status)
    row = store.get_experiment(exp["id"])
    assert row is not None
    return row


def seed_store(store: Store) -> None:
    """Seed the Store with the demo fixture experiment and Agent D's synthetic fixtures."""
    # Avoid pytest-xstyle double-import reseeding: skip if already seeded
    if store.get_experiment(DEMO_EXPERIMENT_ID):
        return

    from api.fixtures import build_fixture_experiment

    persist_experiment_dict(store, build_fixture_experiment(DEMO_EXPERIMENT_ID))

    profile = Profile.from_dict(_load_json(SYNTHETIC_DIR / "synthetic_profile.json"))
    selection = Selection.from_dict(_load_json(SYNTHETIC_DIR / "synthetic_selection.json"))
    pairs_raw = _load_json(SYNTHETIC_DIR / "synthetic_validation_pairs.json")
    exp_dict = {
        "id": SYNTHETIC_EXPERIMENT_ID,
        "workload_id": profile.workload_name or "clean_build",
        "objective": selection.objective_mode or "deadline",
        "runtime_budget_s": selection.deadline_s,
        "preference": None,
        "profile": profile.to_dict(),
        "selection": selection.to_dict(),
        "validation": {"pairs": list(pairs_raw)},
    }
    persist_experiment_dict(store, exp_dict)

    for cal_raw in _load_json(SYNTHETIC_DIR / "synthetic_calibration_records.json"):
        store.record_calibration(CalibrationRecord.from_dict(cal_raw))


# ---------------------------------------------------------------------------
# Model-shaped records -> frozen API shapes (docs/API.md)
# ---------------------------------------------------------------------------

def selection_to_api(sel: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Adapt a core.models.Selection dict to the API/frontend selection shape.

    Additive-only: all Selection model fields are preserved alongside the
    contract fields (config_id, objective, metrics, preference_outcomes).
    """
    if not sel:
        return {}
    status = sel.get("status", "")
    selected_id = sel.get("selected_config_id")
    state = sel.get("preference_outcome_state")
    e_red = sel.get("energy_reduction_pct")
    t_inc = sel.get("runtime_increase_pct")

    energy_met = {"both_met": True, "closest_energy_target": True}.get(state, status == "selected")
    perf_met = {"both_met": True, "closest_perf_floor": True}.get(state, status == "selected")

    candidates = sel.get("candidate_summaries") or []
    usable = [
        c
        for c in candidates
        if c.get("profile_is_usable") and c.get("median_energy_j") is not None and c.get("runtime_samples")
    ]
    closest_energy_id = (
        min(usable, key=lambda c: (c["median_energy_j"], c["config_id"]))["config_id"] if usable else None
    )
    closest_perf_id = (
        min(usable, key=lambda c: (min(c["runtime_samples"]) if c["runtime_samples"] else float("inf"), c["config_id"]))["config_id"]
        if usable
        else None
    )

    api: dict[str, Any] = {
        "config_id": selected_id,
        "selected_config_id": selected_id,
        "objective": sel.get("objective_mode"),
        "status": status,
        "status_message": sel.get("status_message"),
        "runtime_budget_s": sel.get("deadline_s"),
        "target_met": status == "selected",
        "savings_vs_baseline_pct": round(e_red, 1) if e_red is not None else None,
        "runtime_vs_baseline_pct": round(t_inc, 1) if t_inc is not None else None,
        "deadline_s": sel.get("deadline_s"),
        "margin": sel.get("margin"),
        "frontier_config_ids": sel.get("frontier_config_ids", []),
        "metrics": {
            "median_runtime_s": sel.get("selected_median_runtime_s"),
            "guarded_runtime_s": sel.get("selected_guarded_runtime_s"),
            "median_energy_j": sel.get("selected_median_energy_j"),
            "energy_savings_pct": round(e_red, 1) if e_red is not None else 0.0,
        },
        "preference_outcomes": {
            "energy_target_met": energy_met,
            "perf_floor_met": perf_met,
            "closest_energy_config_id": selected_id if energy_met else closest_energy_id,
            "closest_perf_config_id": selected_id if perf_met else closest_perf_id,
        },
        # Additive: full model fields for grounded explanations and honest edge states
        "selected_median_energy_j": sel.get("selected_median_energy_j"),
        "selected_median_runtime_s": sel.get("selected_median_runtime_s"),
        "selected_guarded_runtime_s": sel.get("selected_guarded_runtime_s"),
        "baseline_config_id": sel.get("baseline_config_id"),
        "baseline_median_energy_j": sel.get("baseline_median_energy_j"),
        "baseline_median_runtime_s": sel.get("baseline_median_runtime_s"),
        "energy_reduction_pct": e_red,
        "runtime_increase_pct": t_inc,
        "energy_target_pct": sel.get("energy_target_pct"),
        "perf_floor_pct": sel.get("perf_floor_pct"),
        "preference_outcome_state": state,
        "perf_floor_miss_pct": sel.get("perf_floor_miss_pct"),
        "energy_target_miss_pct": sel.get("energy_target_miss_pct"),
        "candidate_summaries": candidates,
    }
    return api


def validation_to_api(pairs: Optional[list[dict[str, Any]]]) -> dict[str, Any]:
    """Adapt persisted ValidationPair dicts to the API validation summary shape."""
    pairs = pairs or []
    if not pairs:
        return {
            "status": "not_run",
            "pairs": [],
            "verified_savings_pct": None,
            "verified_runtime_delta_s": None,
        }
    e_reds = [p["energy_reduction_pct"] for p in pairs if p.get("energy_reduction_pct") is not None]
    t_deltas = [
        p["selected_run"]["runtime_s"] - p["baseline_run"]["runtime_s"]
        for p in pairs
        if p.get("selected_run") and p.get("baseline_run")
    ]
    all_ok = all(p.get("both_succeeded") for p in pairs)
    met_budget = all(p.get("met_budget") for p in pairs)
    status = "verified" if (all_ok and met_budget) else ("partial" if all_ok else "failed")
    return {
        "status": status,
        "pairs": pairs,
        "verified_savings_pct": round(median(e_reds), 1) if e_reds else None,
        "verified_runtime_delta_s": round(median(t_deltas), 2) if t_deltas else None,
    }


def experiment_to_api(row: dict[str, Any]) -> dict[str, Any]:
    """Adapt a Store experiment row into the frozen GET /api/experiments/{id} shape."""
    profile = row.get("profile") or {}
    profile.setdefault("configurations", {})
    profile.setdefault("runs", [])
    return {
        "id": row["id"],
        "state": row["state"],
        "created_at": row["created_at"],
        "workload_id": row["workload_name"],
        "objective": row["objective"],
        "runtime_budget_s": row["runtime_budget_s"],
        "preference": row.get("preference"),
        "profile": profile,
        "selection": selection_to_api(row.get("selection")),
        "validation": validation_to_api(row.get("validation")),
        "restoration_status": row.get("restoration_status", "not_required"),
        # Additive: persisted state-machine history for restore-status transparency
        "state_transitions": row.get("state_transitions", []),
    }


def experiment_summary_to_api(row: dict[str, Any]) -> dict[str, Any]:
    """Adapt a Store experiment row into the frozen GET /api/experiments list shape."""
    sel = selection_to_api(row.get("selection"))
    return {
        "id": row["id"],
        "workload_id": row["workload_name"],
        "state": row["state"],
        "created_at": row["created_at"],
        "selected_config_id": sel.get("config_id") or "",
        "baseline_energy_j": sel.get("baseline_median_energy_j"),
        "baseline_runtime_s": sel.get("baseline_median_runtime_s"),
        "selected_energy_j": sel.get("selected_median_energy_j"),
        "selected_runtime_s": sel.get("selected_median_runtime_s"),
        "energy_saved_pct": sel.get("savings_vs_baseline_pct"),
    }


def apply_live_profile(
    overlay: dict[str, Any],
    exp_id: str,
    runs: list[dict[str, Any]],
    configurations: dict[str, dict[str, Any]],
    selection: Any,
    profile_source: str,
) -> None:
    """Merge live-engine results into an experiment overlay dict (in place).

    The overlay is the API-shaped experiment returned by GET /experiments/{id};
    this swaps its fixture profile/selection for measured values, labeled with
    profile_source ("calibration" | "fresh_runs"), and reuses selection_to_api
    for the contract shape.
    """
    sel_dict = selection
    if hasattr(selection, "to_dict"):  # B's dataclass contract
        sel_dict = selection.to_dict()
    elif hasattr(selection, "model_dump"):  # pydantic models
        sel_dict = selection.model_dump()

    profile = overlay.setdefault("profile", {})
    profile["configurations"] = configurations
    profile["runs"] = runs
    profile["baseline_config_id"] = next(iter(configurations), None)
    overlay["selection"] = selection_to_api(sel_dict)
    overlay["_selection_model"] = sel_dict
    overlay["state"] = "selected"
    overlay["profile_source"] = profile_source
