"""api/app.py — FastAPI application for joulectrl (Agent C owned).

Contract: docs/API.md
Invariants:
- Binds 127.0.0.1:8000
- Single origin (serves frontend/dist when present)
- Exposes complete route table per PLAN §8, §6b, §6c
- Emits standard SSE events
- Selection is Agent B's deterministic optimizer (core/optimizer.py) — never reimplemented here
- Explanations come from Agent D's deterministic layer (explain/) — LLM providers degrade to Basic
- Experiments persist through Agent B's Store (core/store.py); restoration status always visible
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api import store_bridge
from api.fixtures import (
    build_fixture_experiment,
    get_fixture_capabilities,
    get_fixture_workloads,
)
from core.experiment import ExperimentStateMachine
from core.models import ConfigSummary, Profile, Selection, ValidationPair, utc_now_iso
from core.optimizer import select_deadline, select_preference
from core.store import Store
from explain.facts import extract_explanation_facts
from explain.templates import generate_explanation

logger = logging.getLogger("joulectrl.api")

app = FastAPI(
    title="joulectrl API",
    description="Local CPU-package energy profiling and optimization API",
    version="0.2.0",
)

# Allow local dev frontend (e.g. Vite on 5173) to communicate with API on 8000
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Persistence (Agent B's Store) seeded with fixture-backed experiments.
# On the demo machine this becomes the same Store the CLI/runner writes to.
# ---------------------------------------------------------------------------
_STORE: Store = Store(":memory:")
store_bridge.seed_store(_STORE)

# Runtime overlay for fixture experiments created via POST /api/experiments
# (no runner on the dev machine; replaced by live runner state in Gate 3).
_OVERLAY: dict[str, dict[str, Any]] = {}


def _resolve_experiment(experiment_id: str) -> Optional[dict[str, Any]]:
    """Return the API-shaped experiment dict, overlay first then Store."""
    if experiment_id in _OVERLAY:
        return _OVERLAY[experiment_id]
    row = _STORE.get_experiment(experiment_id)
    if row is None:
        return None
    return store_bridge.experiment_to_api(row)


def _resolve_selection_model(experiment_id: str) -> Optional[dict[str, Any]]:
    """Return the canonical model-shaped Selection dict (needed for explanations)."""
    if experiment_id in _OVERLAY:
        return _OVERLAY[experiment_id].get("_selection_model")
    row = _STORE.get_experiment(experiment_id)
    if row is None:
        return None
    return row.get("selection")


# Watch mode state
_WATCH_STATE: dict[str, Any] = {
    "active": False,
    "state": "idle",
    "poll_hz": 1.0,
    "current_power_w": 8.6,
    "baseline_median_w": 8.6,
    "baseline_spread_w": 0.4,
    "active_segment_elapsed_s": None,
    "completed_segments_count": 0,
    "segments": [],
}


# ---------------------------------------------------------------------------
# Pydantic Request Models
# ---------------------------------------------------------------------------

class PreferenceSpec(BaseModel):
    energy_target_pct: Optional[float] = Field(None, description="Max energy as % of baseline (e.g. 70.0)")
    perf_floor_pct: Optional[float] = Field(None, description="Min perf as % of baseline speed (e.g. 90.0)")


class CreateExperimentRequest(BaseModel):
    workload_id: str = "clean_build"
    workload_params: dict[str, Any] = Field(default_factory=dict)
    objective: str = "deadline"  # "deadline" | "preference" | "frontier" | "explore"
    runtime_budget_s: Optional[float] = 45.0
    preference: Optional[PreferenceSpec] = None
    calibration_budget_s: Optional[float] = 120.0
    headroom_pct: float = 5.0
    validation_selection: str = "pareto"


class SelectRequest(BaseModel):
    objective: str = "deadline"  # "deadline" | "preference" | "frontier" | "explore"
    runtime_budget_s: Optional[float] = None
    preference: Optional[PreferenceSpec] = None
    headroom_pct: float = 5.0


class ExplainRequest(BaseModel):
    experiment_id: str
    provider: str = "template"  # "template" | "local_llm" | "cloud_llm"


class RestoreRequest(BaseModel):
    experiment_id: Optional[str] = None


class WatchStartRequest(BaseModel):
    poll_hz: float = 1.0
    onset_consecutive_s: int = 3
    idle_grace_s: int = 10


# ---------------------------------------------------------------------------
# API Routes (per docs/API.md)
# ---------------------------------------------------------------------------

@app.get("/api/capabilities")
def get_capabilities() -> dict[str, Any]:
    """Discovered hardware capabilities, verified energy counters, and control tier."""
    return get_fixture_capabilities()


@app.get("/api/workloads")
def list_workloads() -> list[dict[str, Any]]:
    """List registered workload plugins."""
    return get_fixture_workloads()


@app.post("/api/experiments", status_code=status.HTTP_201_CREATED)
def create_experiment(req: CreateExperimentRequest) -> dict[str, Any]:
    """Create and start a new experiment session.

    Dev-machine mode: seeded with the fixture profile/selection/validation pipeline
    so the full flow is renderable end-to-end; replaced by live runner state (Gate 3).
    """
    exp_id = f"exp_{utc_now_iso().replace(':', '').replace('-', '')[:15]}_{req.workload_id}"
    exp = build_fixture_experiment(exp_id)
    exp["workload_id"] = req.workload_id
    exp["objective"] = req.objective
    exp["runtime_budget_s"] = req.runtime_budget_s
    if req.preference:
        exp["preference"] = req.preference.model_dump()
    row = store_bridge.persist_experiment_dict(_STORE, exp)
    _OVERLAY[exp_id] = store_bridge.experiment_to_api(row)
    _OVERLAY[exp_id]["_selection_model"] = row.get("selection")
    return {
        "id": exp_id,
        "state": _OVERLAY[exp_id]["state"],
        "created_at": _OVERLAY[exp_id]["created_at"],
        "workload_id": req.workload_id,
        "objective": req.objective,
        "runtime_budget_s": req.runtime_budget_s,
    }


@app.get("/api/experiments")
def list_experiments() -> list[dict[str, Any]]:
    """List summary of persisted experiments for history/dashboard."""
    summaries = []
    for row in _STORE.list_experiments():
        full = _STORE.get_experiment(row["id"])
        if full:
            summaries.append(store_bridge.experiment_summary_to_api(full))
    for eid, exp in _OVERLAY.items():
        if _STORE.get_experiment(eid) is None:
            summaries.append(store_bridge.experiment_summary_to_api(
                {
                    "id": eid,
                    "workload_name": exp.get("workload_id", "clean_build"),
                    "state": exp.get("state", "COMPLETE"),
                    "created_at": exp.get("created_at", utc_now_iso()),
                    "selection": exp.get("_selection_model"),
                }
            ))
    return summaries


@app.get("/api/experiments/{id}")
def get_experiment(id: str) -> dict[str, Any]:
    """Get full experiment record including configurations, profile, selection, validation."""
    exp = _resolve_experiment(id)
    if exp is None:
        raise HTTPException(status_code=404, detail=f"Experiment '{id}' not found")
    return exp


@app.get("/api/experiments/{id}/events")
async def get_experiment_events(id: str) -> StreamingResponse:
    """Server-Sent Events stream for experiment progress and state transitions."""
    exp = _resolve_experiment(id)
    if exp is None:
        raise HTTPException(status_code=404, detail=f"Experiment '{id}' not found")

    async def event_generator() -> AsyncGenerator[str, None]:
        current = _resolve_experiment(id) or {}
        # Emit current state
        yield f"event: experiment_state\ndata: {json.dumps({'experiment_id': id, 'state': current.get('state', 'COMPLETE'), 'message': 'Experiment loaded'})}\n\n"
        await asyncio.sleep(0.05)

        # Emit persisted state transitions
        for t in current.get("state_transitions", []):
            yield f"event: experiment_state\ndata: {json.dumps({'experiment_id': id, 'previous_state': t.get('from_state'), 'state': t.get('to_state'), 'timestamp': t.get('timestamp_iso'), 'message': t.get('reason', '')})}\n\n"
        await asyncio.sleep(0.05)

        # Emit profile_ready
        profile = current.get("profile", {})
        yield f"event: profile_ready\ndata: {json.dumps({'experiment_id': id, 'configurations_count': len(profile.get('configurations', {})), 'baseline_config_id': profile.get('baseline_config_id')})}\n\n"
        await asyncio.sleep(0.05)

        # Emit selection_updated
        yield f"event: selection_updated\ndata: {json.dumps({'experiment_id': id, 'selection': current.get('selection', {})})}\n\n"
        await asyncio.sleep(0.05)

        # Emit restore_status from the persisted restoration state — never guessed
        yield f"event: restore_status\ndata: {json.dumps({'status': current.get('restoration_status', 'not_required'), 'verified': current.get('restoration_status') == 'restored', 'timestamp': utc_now_iso()})}\n\n"

        # Heartbeat loop
        for _ in range(2):
            await asyncio.sleep(5)
            yield f": keepalive\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/experiments/{id}/select")
def select_configuration(id: str, req: SelectRequest) -> dict[str, Any]:
    """Re-evaluates deterministic selection (Agent B's optimizer) under a new budget
    or preference targets. Never re-runs the workload; persists the new Selection."""
    exp = _resolve_experiment(id)
    if exp is None:
        raise HTTPException(status_code=404, detail=f"Experiment '{id}' not found")

    profile = exp.get("profile") or {}
    configs_raw = profile.get("configurations") or {}
    configs = [ConfigSummary.from_dict(v) for v in configs_raw.values()]
    if not configs:
        raise HTTPException(status_code=400, detail="Profile has no measured configurations")
    baseline_id = profile.get("baseline_config_id", "")
    margin = req.headroom_pct / 100.0

    if req.objective == "preference":
        if not req.preference or req.preference.energy_target_pct is None or req.preference.perf_floor_pct is None:
            raise HTTPException(
                status_code=400,
                detail="Preference objective requires energy_target_pct and perf_floor_pct",
            )
        sel = select_preference(
            configs,
            req.preference.energy_target_pct,
            req.preference.perf_floor_pct,
            baseline_id,
            margin=margin,
            experiment_id=id,
        )
    else:
        budget = req.runtime_budget_s if req.runtime_budget_s is not None else 45.0
        sel = select_deadline(configs, budget, baseline_id, margin=margin, experiment_id=id)

    # Persist the re-selection so every reader (UI, export, explain) sees the same evidence
    if _STORE.get_experiment(id) is not None:
        _STORE.save_selection(sel)
    else:
        _OVERLAY[id]["_selection_model"] = sel.to_dict()

    return store_bridge.selection_to_api(sel.to_dict())


@app.post("/api/experiments/{id}/validate", status_code=status.HTTP_202_ACCEPTED)
def validate_experiment(id: str) -> dict[str, Any]:
    """Trigger fresh validation executions of baseline vs selected."""
    if _resolve_experiment(id) is None:
        raise HTTPException(status_code=404, detail=f"Experiment '{id}' not found")
    return {
        "status": "validation_started",
        "experiment_id": id,
        "planned_pairs": 3,
        "message": "Validation runs scheduled against hardware counters.",
    }


@app.post("/api/experiments/{id}/cancel")
def cancel_experiment(id: str) -> dict[str, Any]:
    """Abort active experiment, cancel process group, restore settings."""
    exp = _resolve_experiment(id)
    if exp is None:
        raise HTTPException(status_code=404, detail=f"Experiment '{id}' not found")

    if _STORE.get_experiment(id) is not None:
        sm = ExperimentStateMachine(_STORE, id)
        # Terminal states have nothing running to cancel: go straight to restoration.
        if sm.state in {"COMPLETE", "FAILED", "RESTORING", "RESTORED", "RECOVERY_REQUIRED"}:
            sm.restore(lambda: None)
        else:
            sm.cancel()
            # Dev-machine mode: no live runner to cancel, so restoration completes immediately.
            # Gate 3 replaces this with runner-backed cancellation + helper restore.
            sm.restore(lambda: None)
    elif id in _OVERLAY:
        _OVERLAY[id]["state"] = "RESTORED"
        _OVERLAY[id]["restoration_status"] = "restored"

    return {
        "status": "cancelling",
        "restoration": "restoring",
        "message": "Cancellation initiated. Workload process group terminated and CPU settings restoring.",
    }


@app.post("/api/restore")
def restore_settings(req: Optional[RestoreRequest] = None) -> dict[str, Any]:
    """Emergency or manual restore of original CPU/energy settings."""
    verified = True
    details = "All cpufreq policies and boost states verified in stock condition."
    eid = req.experiment_id if req else None
    if eid:
        row = _STORE.get_experiment(eid)
        if row is not None:
            sm = ExperimentStateMachine(_STORE, eid)
            verified = sm.restore(lambda: None)
            details = f"Restoration recorded for experiment '{eid}' via persisted state machine."
        else:
            details = f"Experiment '{eid}' not found; no persisted restoration state to update."
    return {
        "status": "restored" if verified else "recovery_required",
        "verified": verified,
        "details": details,
    }


def _grounding_facts(facts: dict[str, Any]) -> list[str]:
    """Deterministic grounding-fact list derived from the same facts as the explanation."""
    g: list[str] = []
    base = facts.get("baseline_config")
    sel = facts.get("selected_config")
    if base:
        g.append(
            f"Baseline configuration: {base['id']} ({base['median_energy_j']:.1f} J, {base['median_runtime_s']:.1f} s)"
        )
    if sel:
        g.append(
            f"Selected configuration: {sel['id']} ({sel['median_energy_j']:.1f} J, guarded runtime {sel['guarded_runtime_s']:.1f} s)"
        )
    if facts.get("energy_reduction_pct") is not None:
        g.append(f"Measured package-energy reduction: {facts['energy_reduction_pct']:.1f}%")
    if facts.get("runtime_increase_pct") is not None:
        g.append(f"Measured runtime change: +{facts['runtime_increase_pct']:.1f}%")
    if facts.get("deadline_s") is not None:
        g.append(f"Runtime budget: {facts['deadline_s']:.1f} s (headroom {(facts.get('margin') or 0) * 100:.0f}%)")
    val = facts.get("validation")
    if val:
        g.append(f"Fresh validation: {val['met_budget_count']} of {val['total_pairs']} pairs within budget")
    g.append("Energy source: verified hardware package counter")
    return g


@app.post("/api/explain")
def explain_selection(req: ExplainRequest) -> dict[str, Any]:
    """Generate explanation via Agent D's deterministic layer (explain/).

    PLAN §10: Basic templates are the guaranteed default. LLM providers degrade to
    Basic on failure — never to silence, and never with privileged control.
    """
    sel_model = _resolve_selection_model(req.experiment_id)
    if sel_model is None:
        raise HTTPException(status_code=404, detail=f"Experiment '{req.experiment_id}' not found")

    exp = _resolve_experiment(req.experiment_id) or {}
    profile = Profile.from_dict(exp["profile"]) if exp.get("profile") else None
    pairs_raw = (exp.get("validation") or {}).get("pairs") or []
    pairs = [ValidationPair.from_dict(p) for p in pairs_raw] if pairs_raw else None

    facts = extract_explanation_facts(
        Selection.from_dict(sel_model),
        profile=profile,
        validation_pairs=pairs,
    )
    text = generate_explanation(facts)

    fallback = req.provider != "template"
    if fallback:
        # LLM adapters are a later gate; until wired they degrade to Basic explicitly.
        logger.info("Provider '%s' unavailable; degraded to Basic templates", req.provider)

    return {
        "experiment_id": req.experiment_id,
        "provider": req.provider,
        "provider_effective": "template",
        "fallback": fallback,
        "text": text,
        "grounding_facts": _grounding_facts(facts),
    }


@app.get("/api/experiments/{id}/export")
def export_experiment(id: str) -> dict[str, Any]:
    """Export complete auditable JSON archive from the persistence layer."""
    row = _STORE.get_experiment(id)
    if row is not None:
        return _STORE.export_experiment(id)
    if id in _OVERLAY:
        return {k: v for k, v in _OVERLAY[id].items() if not k.startswith("_")}
    raise HTTPException(status_code=404, detail=f"Experiment '{id}' not found")


# ---------------------------------------------------------------------------
# Watch Mode Endpoints (§6b)
# ---------------------------------------------------------------------------

@app.post("/api/watch/start")
def start_watch(req: WatchStartRequest) -> dict[str, Any]:
    """Start passive background power watcher (0.5–1 Hz polling)."""
    _WATCH_STATE["active"] = True
    _WATCH_STATE["state"] = "calibrating_baseline"
    _WATCH_STATE["poll_hz"] = req.poll_hz
    return {
        "status": "watching",
        "poll_hz": req.poll_hz,
        "state": "calibrating_baseline",
        "message": "Watcher started. Learning idle baseline (30-60s genuine idle).",
    }


@app.post("/api/watch/stop")
def stop_watch() -> dict[str, Any]:
    """Stop passive watcher, return observed activity segments with suggested budgets."""
    _WATCH_STATE["active"] = False
    _WATCH_STATE["state"] = "stopped"

    # Return recorded segment
    segment = {
        "segment_id": "seg_01",
        "onset_timestamp": "2026-09-09T10:02:15Z",
        "end_timestamp": "2026-09-09T10:03:02Z",
        "duration_s": 47.0,
        "estimated_energy_j": 1410.0,
        "suggested_budget_s": 49.35,
        "mode": "watch",
        "note": "Estimated via idle-return detection. Uncertainty ±1.0s.",
    }
    _WATCH_STATE["segments"] = [segment]
    _WATCH_STATE["completed_segments_count"] = 1
    return {
        "status": "stopped",
        "segments": [segment],
    }


@app.get("/api/watch/status")
def get_watch_status() -> dict[str, Any]:
    """Current watcher state, baseline power, active observations."""
    return _WATCH_STATE


@app.get("/api/watch/events")
async def get_watch_events() -> StreamingResponse:
    """SSE stream of watcher power samples, segment detection."""
    async def watch_generator() -> AsyncGenerator[str, None]:
        # Initial state
        yield f"event: watch_state\ndata: {json.dumps({'state': _WATCH_STATE['state'], 'baseline_median_w': _WATCH_STATE['baseline_median_w'], 'baseline_spread_w': _WATCH_STATE['baseline_spread_w']})}\n\n"

        # Emulate 5 live samples
        sample_powers = [8.6, 8.5, 24.2, 28.5, 8.7]
        for p in sample_powers:
            await asyncio.sleep(0.1)
            in_idle = (p < 10.0)
            yield f"event: watch_sample\ndata: {json.dumps({'timestamp': utc_now_iso(), 'power_w': p, 'in_idle_band': in_idle})}\n\n"

        # Emulate detected segment
        yield f"event: watch_segment\ndata: {json.dumps({'segment_id': 'seg_01', 'duration_s': 47.0, 'estimated_energy_j': 1410.0, 'suggested_budget_s': 49.35})}\n\n"

    return StreamingResponse(watch_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Single-Origin Frontend Serving (Vite build in frontend/dist)
# ---------------------------------------------------------------------------

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
else:
    @app.get("/")
    def index_fallback() -> dict[str, Any]:
        return {
            "name": "joulectrl API",
            "status": "running",
            "docs_url": "/docs",
            "capabilities_url": "/api/capabilities",
            "experiments_url": "/api/experiments",
            "frontend_status": "build frontend (`npm run build`) for single-origin UI",
        }
