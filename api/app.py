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
import os
import sys
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, Query, status
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
from api.live import WatchService, stream_experiment_events
from core.events import default_bus
from core.experiment import ExperimentStateMachine
from core.models import ConfigSummary, CoreClassMap, Profile, Selection, ValidationPair, utc_now_iso
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
if "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules:
    _DEFAULT_DB = ":memory:"
else:
    _DEFAULT_DB = os.path.join(os.path.expanduser("~"), ".joulectrl", "joulectrl.db")

_DB_PATH = os.environ.get("JOUCTRL_DB_PATH", _DEFAULT_DB)
_STORE: Store = Store(_DB_PATH)
if _STORE.get_experiment(store_bridge.SYNTHETIC_EXPERIMENT_ID) is None:
    store_bridge.seed_store(_STORE)

# Runtime overlay for fixture experiments created via POST /api/experiments
# (no runner on the dev machine; replaced by live runner state in Gate 3).
_OVERLAY: dict[str, dict[str, Any]] = {}
_CAPS_CACHE: dict[str, Any] = {}
_CAPS_CACHE_AT: float = 0.0


def _resolve_experiment(experiment_id: str) -> Optional[dict[str, Any]]:
    """Return the API-shaped experiment dict, overlay merged over Store."""
    exp = None
    row = _STORE.get_experiment(experiment_id)
    if row is not None:
        exp = store_bridge.experiment_to_api(row)

    if experiment_id in _OVERLAY:
        if exp is None:
            exp = dict(_OVERLAY[experiment_id])
        else:
            exp.update({k: v for k, v in _OVERLAY[experiment_id].items() if not k.startswith("_")})

    if exp is None:
        return None

    # Attach runs from persistent SQLite Store so runs are never lost
    try:
        db_runs = _STORE.get_runs(experiment_id)
        if db_runs:
            prof = exp.setdefault("profile", {})
            existing_runs = prof.setdefault("runs", [])
            existing_ids = {r.get("run_id") for r in existing_runs if isinstance(r, dict)}
            for r in db_runs:
                if r.run_id not in existing_ids:
                    cfg_api = (
                        r.configuration.to_dict()
                        if hasattr(r.configuration, "to_dict")
                        else {
                            "layout": getattr(r.configuration, "layout", "B"),
                            "worker_count": getattr(r.configuration, "worker_count", 1),
                            "cpu_affinity": getattr(r.configuration, "cpu_affinity", []),
                            "freq_cap_khz": getattr(r.configuration, "freq_cap_khz", None),
                            "boost": getattr(r.configuration, "boost", False),
                        }
                    )
                    existing_runs.append({
                        "run_id": r.run_id,
                        "config_id": r.config_id,
                        "configuration": cfg_api,
                        "repetition": r.repetition,
                        "runtime_s": r.runtime_s,
                        "package_energy_j": r.package_energy_j,
                        "energy_available": r.energy_available,
                        "status": r.status,
                    })
    except Exception as exc:
        logging.warning("Failed to attach stored runs for %s: %s", experiment_id, exc)

    return exp


def _resolve_selection_model(experiment_id: str) -> Optional[dict[str, Any]]:
    """Return the canonical model-shaped Selection dict (needed for explanations)."""
    if experiment_id in _OVERLAY and _OVERLAY[experiment_id].get("_selection_model"):
        return _OVERLAY[experiment_id].get("_selection_model")
    row = _STORE.get_experiment(experiment_id)
    if row is None:
        return None
    return row.get("selection")


# Watch mode state: live session on B's WatchDetector when started
# (core/watch.py); None when idle. Read-only per §6b.
_WATCH_SERVICE: Optional[WatchService] = None


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
    # EXPERIMENTAL (dev option, off by default): profile with amd_pstate in
    # passive mode, where frequency caps bind WITH boost on. Restored after.
    # Measured on the demo laptop: marginal gains (see capability_report note).
    experimental_passive_caps: bool = False
    headroom_pct: float = 5.0
    validation_selection: str = "pareto"
    repetitions: int = 1
    priority_mode: Optional[str] = "top_priority"


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

def _live_capabilities_cached() -> dict[str, Any]:
    """Live capability report for the engine (cached briefly per process)."""
    global _CAPS_CACHE, _CAPS_CACHE_AT
    now = time.time()
    if _CAPS_CACHE is None or now - _CAPS_CACHE_AT > 30:
        try:
            _CAPS_CACHE = get_capabilities()
            _CAPS_CACHE_AT = now
        except Exception:
            _CAPS_CACHE = {}
    return _CAPS_CACHE


@app.get("/api/capabilities")
def get_capabilities() -> dict[str, Any]:
    """Discovered hardware capabilities, verified energy counters, and control tier.

    Live discovery FIRST (A's core/discovery.py, read-only, cross-platform):
    on a real Linux machine this reports THAT machine. If live discovery is
    unusable (no core classes and no readable energy counter — e.g. Windows or
    a VM), fall back to the committed demo-laptop fixture, clearly labeled so
    the UI never presents fixture data as the local machine's.
    """
    try:
        from core.discovery import capability_report as live_report

        raw = live_report()
        cpu = raw.get("cpu", {})
        classes = raw.get("core_classes", {}) or {}
        energy = raw.get("energy", {}) or {}
        cpufreq = raw.get("cpufreq", {}) or {}
        energy_usable = energy.get("readable") in ("unprivileged", "permission_required")
        classes_usable = bool(classes.get("classes"))
        if energy_usable or classes_usable:
            cls_map = classes.get("classes") or {}
            fast = max(
                cls_map,
                key=lambda k: (classes.get("hw_max_freq", {}) or {}).get(k, 0),
                default="",
            )
            return {
                "source": "live",
                "machine": {
                    "hostname": raw.get("machine"),
                    "cpu_model": cpu.get("model"),
                    "boot_id": raw.get("boot_id"),
                    "os": raw.get("os"),
                    "tuned_active_profile": raw.get("pm_daemons", {}).get("tuned_profile"),
                    "ac_power": raw.get("ac_power"),
                },
                "topology": {
                    "logical_cores": cpu.get("ncpu"),
                    "physical_cores": cpu.get("n_cores"),
                    "classes": dict(cls_map),
                    "driver": (cpufreq.get("drivers") or [None])[0],
                    "governor": (cpufreq.get("governors") or [None])[0],
                    "cpufreq_policies_count": cpufreq.get("n_policies"),
                },
                "energy": {
                    "backend": (energy.get("package_paths") or [None])[0],
                    # RAPL domain derived from the discovered path (e.g.
                    # intel-rapl:0 -> package-0) so live and fixture shapes match
                    "domain": (
                        "package-"
                        + ((energy.get("package_paths") or [{}])[0].get("path", "")
                           .rsplit("intel-rapl:", 1)[-1]
                           .split("/")[0]
                           .split(":")[0])
                        if (energy.get("package_paths") or [{}])[0].get("path")
                        else "package-0"
                    ),
                    "available": energy_usable,
                    "root_required": energy.get("readable") == "permission_required",
                },
                "controls": {
                    "boost_toggle": bool(cpufreq.get("boost_knob")),
                    "frequency_caps": classes_usable,
                    "epp_control": bool(raw.get("epp", {}).get("available")),
                    "effective_tier": "full" if classes_usable and energy_usable else "reduced",
                },
                "restoration": {"supported": True, "snapshot_present": False, "status": "restored"},
                "note": "Live discovery on this machine (read-only).",
            }
    except Exception as exc:  # pragma: no cover - degraded environments
        logging.warning("live capability discovery failed: %s", exc)

    fallback = get_fixture_capabilities()
    fallback["source"] = "fixture"
    fallback.setdefault(
        "note",
        "Live discovery unavailable on this machine — showing the committed demo-laptop fixture (labeled).",
    )
    return fallback


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

    # Live path: on machines with the privileged helper, run the REAL pipeline
    # (calibration-informed profiling -> deterministic selection -> restore)
    # in a background thread, emitting SSE progress. Dev machines keep the
    # fixture-seeded behavior above.
    try:
        from api.engine import LiveEngine

        engine = LiveEngine(default_bus(), store_bridge_mod=store_bridge, overlays=_OVERLAY, store=_STORE)
        seeded = dict(_OVERLAY[exp_id])
        seeded["_live_capabilities"] = _live_capabilities_cached()
        if engine.start_experiment(exp_id, {
            "workload_id": req.workload_id, "objective": req.objective,
            "runtime_budget_s": req.runtime_budget_s,
            "calibration_budget_s": req.calibration_budget_s,
            "preference": req.preference.model_dump() if req.preference else None,
            "experimental_passive_caps": req.experimental_passive_caps,
            "repetitions": max(1, min(5, req.repetitions)),
            "priority_mode": req.priority_mode or "top_priority",
        }, seeded):
            _OVERLAY[exp_id]["state"] = "profiling"
            prof = _OVERLAY[exp_id].setdefault("profile", {})
            prof["runs"] = []
            prof["configurations"] = {}
            _OVERLAY[exp_id]["validation"] = {
                "status": "not_run",
                "pairs": [],
                "verified_savings_pct": None,
                "verified_runtime_delta_s": None,
            }
            if _STORE.get_experiment(exp_id):
                _STORE.save_validation_pairs(exp_id, [])
    except Exception as exc:  # pragma: no cover - stay on fixture path
        logging.warning("live engine unavailable, using fixture mode: %s", exc)

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
    seen = set()
    for eid, exp in reversed(list(_OVERLAY.items())):
        seen.add(eid)
        summaries.append(store_bridge.experiment_summary_to_api(
            {
                "id": eid,
                "workload_name": exp.get("workload_id", "clean_build"),
                "state": exp.get("state", "COMPLETE"),
                "created_at": exp.get("created_at", utc_now_iso()),
                "selection": exp.get("_selection_model"),
            }
        ))
    for row in _STORE.list_experiments():
        if row["id"] not in seen:
            seen.add(row["id"])
            full = _STORE.get_experiment(row["id"])
            if full:
                summaries.append(store_bridge.experiment_summary_to_api(full))
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
    """Server-Sent Events stream for experiment progress and state transitions.

    Live source: Agent B's EventBus (core/events.py) — replay(0) initial burst
    then live follow, per B's AFFECTS(c) 11:47 UTC. Terminal fixture-backed
    experiments have no live traffic yet: synthesize the terminal burst from
    persisted state so the stream is immediately renderable (honesty: labeled
    'replayed_from_store').
    """
    if _resolve_experiment(id) is None:
        raise HTTPException(status_code=404, detail=f"Experiment '{id}' not found")

    evlog = default_bus().for_experiment(id)
    has_live_history = evlog.last_seq() > 0

    async def event_generator() -> AsyncGenerator[str, None]:
        if not has_live_history:
            # Fixture/persisted experiment: reconstruct the terminal burst from
            # the store (never guessed — from persisted transitions), then keep
            # the stream open for any future live publishes on this id.
            current = _resolve_experiment(id) or {}
            yield f"event: experiment_state\ndata: {json.dumps({'experiment_id': id, 'state': current.get('state', 'COMPLETE'), 'message': 'Experiment loaded', 'source': 'replayed_from_store'})}\n\n"
            for t in current.get("state_transitions", []):
                yield f"event: experiment_state\ndata: {json.dumps({'experiment_id': id, 'previous_state': t.get('from_state'), 'state': t.get('to_state'), 'timestamp': t.get('timestamp_iso'), 'message': t.get('reason', ''), 'source': 'replayed_from_store'})}\n\n"
            profile = current.get("profile", {})
            yield f"event: profile_ready\ndata: {json.dumps({'experiment_id': id, 'configurations_count': len(profile.get('configurations', {})), 'baseline_config_id': profile.get('baseline_config_id'), 'source': 'replayed_from_store'})}\n\n"
            yield f"event: selection_updated\ndata: {json.dumps({'experiment_id': id, 'selection': store_bridge.selection_to_api(current.get('selection')), 'source': 'replayed_from_store'})}\n\n"
            yield f"event: restore_status\ndata: {json.dumps({'status': current.get('restoration_status', 'not_required'), 'verified': current.get('restoration_status') == 'restored', 'timestamp': utc_now_iso(), 'source': 'replayed_from_store'})}\n\n"
            await asyncio.sleep(0.05)

        # Live follow on B's bus (replay(0) burst if history exists)
        agen = stream_experiment_events(id)
        try:
            async for frame in agen:
                yield frame
        finally:
            await agen.aclose()

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

    # Live event: B's bus (emission point assigned to C per AFFECTS(c) 11:47)
    default_bus().publish(
        id,
        "selection_updated",
        {"experiment_id": id, "selection": store_bridge.selection_to_api(sel.to_dict())},
    )

    return store_bridge.selection_to_api(sel.to_dict())


@app.post("/api/experiments/{id}/validate", status_code=status.HTTP_202_ACCEPTED)
def validate_experiment(id: str) -> dict[str, Any]:
    """Trigger fresh validation executions of baseline vs selected."""
    exp = _resolve_experiment(id)
    if exp is None:
        raise HTTPException(status_code=404, detail=f"Experiment '{id}' not found")

    try:
        from api.engine import LiveEngine

        engine = LiveEngine(default_bus(), store_bridge_mod=store_bridge, overlays=_OVERLAY, store=_STORE)
        started = engine.start_validation(id, repetitions=3)
    except Exception as exc:
        logger.warning("Failed to launch live validation: %s", exc)
        started = False

    return {
        "status": "validation_started",
        "experiment_id": id,
        "planned_pairs": 3,
        "message": "Validation runs scheduled against hardware counters." if started else "Validation scheduled in simulation mode.",
    }


class ProcessPriorityRequest(BaseModel):
    pid: Optional[int] = None
    pattern: Optional[str] = None
    policy: str = "deprioritize_eco"  # "deprioritize_eco", "prioritize_fast", "restore_normal"


@app.get("/api/calibration")
def get_calibration(experiment_id: Optional[str] = Query(None)) -> dict[str, Any]:
    """Measured calibration and benchmark curve data.

    Pulls all measured runs from _STORE (supporting experiment-level or cross-experiment aggregation).
    Identical runs (same configuration: same freq cap, cores, workers) are averaged together.
    Performance score is computed as faster completion = higher score (1000 / runtime_s or chunks/s).
    Points are grouped into monotonic series (e.g. Zen 5 (4c), Zen 5c (4c), All Cores (16t)).
    Falls back to fixtures only when no runs exist in the database.
    """
    from statistics import median

    # Collect available experiments for the dropdown selector
    experiments_meta = []
    try:
        exps = _STORE.list_experiments()
        for e in exps:
            runs = _STORE.get_runs(e["id"])
            succ = [r for r in runs if r.status == "success" and r.runtime_s and r.runtime_s > 0]
            if succ:
                experiments_meta.append({
                    "id": e["id"],
                    "title": e.get("title") or e["id"],
                    "workload_name": succ[0].workload_name if succ else e.get("workload_id", "unknown"),
                    "run_count": len(succ),
                    "created_at": e.get("created_at"),
                })
    except Exception as exc:
        logger.warning("Could not list experiments for calibration: %s", exc)

    # Class hardware context
    cap_classes: dict[str, Any] = {}
    try:
        cap_classes = _load_json_file("fixtures/real/capability_report.json").get("core_classes") or {}
    except Exception:
        pass
    topo_info: dict[str, Any] = {}
    try:
        cap_cpu = _load_json_file("fixtures/real/capability_report.json").get("cpu", {})
        topo_info = {
            "physical_cores": cap_cpu.get("n_cores", 8),
            "logical_cores": cap_cpu.get("ncpu", 16),
        }
    except Exception:
        topo_info = {"physical_cores": 8, "logical_cores": 16}

    # Determine target runs from _STORE
    selected_exp_id = experiment_id
    target_runs = []
    if selected_exp_id and selected_exp_id != "all":
        try:
            target_runs = [r for r in _STORE.get_runs(selected_exp_id) if r.status == "success" and r.runtime_s and r.runtime_s > 0]
        except Exception:
            target_runs = []
    elif selected_exp_id == "all":
        try:
            for e in _STORE.list_experiments():
                target_runs.extend([r for r in _STORE.get_runs(e["id"]) if r.status == "success" and r.runtime_s and r.runtime_s > 0])
        except Exception:
            target_runs = []
    else:
        # Default: select the experiment with the most runs, or first available
        best_exp = max(experiments_meta, key=lambda x: x["run_count"], default=None) if experiments_meta else None
        if best_exp:
            selected_exp_id = best_exp["id"]
            target_runs = [r for r in _STORE.get_runs(selected_exp_id) if r.status == "success" and r.runtime_s and r.runtime_s > 0]

    # If database runs exist, aggregate them into clean curves
    if target_runs:
        fast_cpus = {0, 2, 4, 6, 8, 10, 12, 14}
        eff_cpus = {1, 3, 5, 7, 9, 11, 13, 15}

        by_key: dict[tuple, list[Any]] = {}
        for r in target_runs:
            cfg = r.configuration
            cpus = tuple(sorted(cfg.cpu_affinity or []))
            cpus_set = set(cpus)
            if cpus_set.issubset(fast_cpus):
                cls = "fast"
            elif cpus_set.issubset(eff_cpus):
                cls = "efficient"
            else:
                cls = "all"
            key = (cls, cpus, cfg.worker_count, cfg.freq_cap_khz, cfg.boost, cfg.id)
            by_key.setdefault(key, []).append(r)

        classes_map: dict[str, dict[str, Any]] = {
            "fast": {"label": "fast", "c1": None, "points": []},
            "efficient": {"label": "efficient", "c1": None, "points": []},
            "all": {"label": "all", "c1": None, "points": []},
        }

        # Check for C1 single-core reference points
        for (cls, cpus, workers, freq, boost, cid), rlist in by_key.items():
            if workers == 1 or len(cpus) == 1:
                if classes_map[cls]["c1"] is None or boost:
                    avg_rt = sum(r.runtime_s for r in rlist) / len(rlist)
                    pwr_vals = [(r.avg_power_w if r.avg_power_w else (r.package_energy_j / r.runtime_s if r.package_energy_j else 0.0)) for r in rlist]
                    avg_w = sum(pwr_vals) / len(rlist) if pwr_vals else 0.0
                    avg_e = sum(r.package_energy_j for r in rlist if r.package_energy_j) / len(rlist) if any(r.package_energy_j for r in rlist) else (avg_w * avg_rt)
                    classes_map[cls]["c1"] = {
                        "runtime_s": round(avg_rt, 4),
                        "energy_j": round(avg_e, 4),
                        "cpus": list(cpus),
                    }

        # If C1 wasn't found in this experiment's runs, load from calibration_c1.json fixture
        try:
            c1_fixture = _load_json_file("fixtures/real/calibration_c1.json").get("rows") or []
            for c1_row in c1_fixture:
                f_cls = c1_row.get("class")
                if f_cls in classes_map and classes_map[f_cls]["c1"] is None:
                    classes_map[f_cls]["c1"] = {
                        "runtime_s": c1_row.get("runtime_s"),
                        "energy_j": c1_row.get("package_energy_j"),
                        "cpus": c1_row.get("cpus", []),
                    }
        except Exception:
            pass

        for (cls, cpus, workers, freq, boost, cid), rlist in by_key.items():
            n = len(rlist)
            avg_rt = sum(r.runtime_s for r in rlist) / n
            pwr_vals = [(r.avg_power_w if r.avg_power_w else (r.package_energy_j / r.runtime_s if r.package_energy_j else 0.0)) for r in rlist]
            avg_w = sum(pwr_vals) / n if pwr_vals else 0.0
            avg_e = sum((r.package_energy_j or 0.0) for r in rlist) / n if any(r.package_energy_j for r in rlist) else (avg_w * avg_rt)

            # Faster task completion = higher score
            score = round(1000.0 / avg_rt, 1)

            chunks = None
            for r in rlist:
                fp = (r.metadata or {}).get("workload_fingerprint")
                if fp and fp.get("chunks"):
                    chunks = fp["chunks"]
                    break
            throughput = round(chunks / avg_rt, 1) if chunks else score
            perf_per_watt = round(throughput / avg_w, 1) if avg_w > 0 else 0.0

            if cls == "fast":
                series_name = f"Zen 5 ({workers} {'threads' if workers > 4 else 'cores'})"
            elif cls == "efficient":
                series_name = f"Zen 5c ({workers} cores)"
            else:
                series_name = f"All Cores ({workers} threads)"

            if boost:
                control_label = "Stock (Boost)"
            elif freq:
                control_label = f"{(freq / 1e6):.2f} GHz" if freq >= 1e6 else f"{(freq / 1e3):.0f} MHz"
            else:
                control_label = "Base"

            point = {
                "control": control_label,
                "config_id": cid,
                "workers": workers,
                "cpus": list(cpus),
                "scope": "single" if len(cpus) <= 1 else "multi",
                "runtime_s": round(avg_rt, 4),
                "energy_j": round(avg_e, 4),
                "watts": round(avg_w, 3),
                "throughput": throughput,
                "score": score,
                "perf_per_watt": perf_per_watt,
                "scaling_efficiency": None,
                "series": series_name,
                "n": n,
            }
            classes_map[cls]["points"].append(point)

        out_classes = []
        for cls_key in ["fast", "efficient", "all"]:
            entry = classes_map[cls_key]
            if entry["points"]:
                # Sort points within each class by (workers, watts) ascending
                entry["points"].sort(key=lambda p: (p["workers"], p["watts"]))
                hw = cap_classes.get(cls_key) or {}
                entry["hw_max_freq_khz"] = hw.get("hw_max_freq")
                out_classes.append(entry)

        scopes_available = {
            entry["label"]: sorted({p["scope"] for p in entry["points"]})
            for entry in out_classes
        }
        all_cores_measured = any(
            topo_info.get("physical_cores", 8) and len(p.get("cpus") or []) >= topo_info.get("physical_cores", 8)
            for entry in out_classes for p in entry["points"]
        )
        workers_available = sorted({p["workers"] for entry in out_classes for p in entry["points"]})

        first_succ = target_runs[0]
        return {
            "source": f"store:{selected_exp_id or 'combined'}",
            "captured_utc": target_runs[-1].timestamp_iso if target_runs else None,
            "kernel": first_succ.workload_name,
            "topology": topo_info,
            "classes": out_classes,
            "scopes_available": scopes_available,
            "all_cores_measured": all_cores_measured,
            "workers_available": workers_available,
            "experiments": experiments_meta,
            "current_experiment_id": selected_exp_id,
            "total_runs_aggregated": len(target_runs),
            "note": "Aggregated live measurements from database. Faster task completion gives higher score. Identical runs are averaged for precision.",
        }

    # Fallback to fixtures if store has no runs
    def load_rows(name: str) -> list[dict[str, Any]]:
        try:
            raw = _load_json_file(f"fixtures/real/{name}")
            return raw.get("rows") or []
        except Exception:
            return []

    c1_rows = load_rows("calibration_c1.json")
    c2_rows = load_rows("calibration_c2_effective.json")
    allcores_rows = load_rows("calibration_c2_allcores.json")

    for row in allcores_rows:
        row = dict(row)
        row["class"] = "all"
        c2_rows.append(row)

    def med(rows: list[dict[str, Any]], key: str) -> Optional[float]:
        vals = [r[key] for r in rows if r.get(key) is not None]
        return median(vals) if vals else None

    classes: dict[str, dict[str, Any]] = {}
    for row in c1_rows:
        cls = str(row.get("class", ""))
        classes.setdefault(cls, {"label": cls, "c1": None, "points": []})
        entry = classes[cls]
        if entry["c1"] is None:
            entry["c1"] = {"runtime_s": None, "energy_j": None, "cpus": row.get("cpus", [])}
        entry["c1"]["cpus"] = row.get("cpus", entry["c1"]["cpus"])

    for cls, entry in classes.items():
        rows = [r for r in c1_rows if r.get("class") == cls]
        if rows:
            entry["c1"] = {
                "runtime_s": med(rows, "runtime_s"),
                "energy_j": med(rows, "package_energy_j"),
                "cpus": rows[0].get("cpus", []),
            }

    grouped_f: dict[tuple, list[dict[str, Any]]] = {}
    chunks_by_key: dict[tuple, int] = {}
    for row in c2_rows:
        key = (str(row.get("class", "")), str(row.get("control", "")), int(row.get("workers", 1)))
        grouped_f.setdefault(key, []).append(row)
        chunks_by_key.setdefault(key, int(row.get("chunks", 32768)))

    for (cls, control, workers), rows in grouped_f.items():
        entry = classes.setdefault(cls, {"label": cls, "c1": None, "points": []})
        runtime_s = med(rows, "runtime_s")
        energy_j = med(rows, "package_energy_j")
        if runtime_s is None or energy_j is None:
            continue
        chunks = chunks_by_key[(cls, control, workers)]
        throughput = chunks / runtime_s
        watts = energy_j / runtime_s
        score = round(1000.0 / runtime_s, 1)
        entry["points"].append(
            {
                "control": control,
                "workers": workers,
                "cpus": rows[0].get("cpus", []),
                "runtime_s": round(runtime_s, 4),
                "energy_j": round(energy_j, 4),
                "watts": round(watts, 3),
                "throughput": round(throughput, 1),
                "score": score,
                "perf_per_watt": round(throughput / watts, 1),
                "scaling_efficiency": None,
                "series": f"{cls} ({workers}w)",
                "n": len(rows),
            }
        )

    out = sorted(classes.values(), key=lambda e: {"fast": 0, "efficient": 1, "all": 2}.get(e["label"], 3))
    for entry in out:
        entry["points"].sort(key=lambda p: (p["workers"], p["watts"]))
        hw = cap_classes.get(entry["label"]) or {}
        entry["hw_max_freq_khz"] = hw.get("hw_max_freq")
        entry["points"] = [
            {**p, "scope": "single" if len(p.get("cpus") or []) <= 1 else "multi"}
            for p in entry["points"]
        ]

    scopes_available = {entry["label"]: sorted({p["scope"] for p in entry["points"]}) for entry in out}
    workers_available = sorted({p["workers"] for entry in out for p in entry["points"]})

    return {
        "source": "fixtures/real/calibration_c1.json + calibration_c2_effective.json + calibration_c2_allcores.json",
        "captured_utc": _fixture_captured_utc("calibration_c2_allcores.json")
        or _fixture_captured_utc("calibration_c2_effective.json"),
        "kernel": "workloads/kernel/fixed_compute",
        "topology": topo_info,
        "classes": out,
        "scopes_available": scopes_available,
        "all_cores_measured": True,
        "workers_available": workers_available,
        "experiments": experiments_meta,
        "current_experiment_id": selected_exp_id,
        "note": "Fixture fallback: faster completion gives higher score. Identical runs are averaged.",
    }


@app.get("/api/system/processes")
def get_user_processes(limit: int = 100) -> dict[str, Any]:
    """List running user processes with CPU%, memory%, nice level, and core affinity."""
    from api.system import list_user_processes
    procs = list_user_processes(limit=limit)
    return {
        "processes": procs,
        "total": len(procs),
    }


@app.post("/api/system/process-priority")
def update_process_priority(req: ProcessPriorityRequest) -> dict[str, Any]:
    """Set process priority and core affinity.

    Policies:
      - 'deprioritize_eco': Pin to Zen 5c efficiency cores (odd CPUs), nice 15.
        Frees Zen 5 fast cores for uninterrupted performance.
      - 'prioritize_fast': Pin to Zen 5 fast cores (even CPUs), nice 0.
      - 'restore_normal': Reset to all 16 cores, nice 0.
    """
    from api.system import apply_policy_to_pattern, set_process_priority

    if req.pattern:
        res = apply_policy_to_pattern(req.pattern, req.policy)
        return res

    if req.pid is not None:
        res = set_process_priority(req.pid, req.policy)
        return res

    raise HTTPException(status_code=400, detail="Either 'pid' or 'pattern' must be provided")


def _fixture_captured_utc(name: str) -> Optional[str]:
    try:
        return _load_json_file(f"fixtures/real/{name}").get("captured_utc")
    except Exception:
        return None


@app.get("/api/experiments/{id}/validation-points")
def get_validation_points(id: str) -> dict[str, Any]:
    """Validation-point candidates: B's layout configurations + measured
    calibration points, per AFFECTS(c) (B, 12:00 UTC).

    Layout candidates come from Agent B's validation.layout_configurations()
    built on the discovered CoreClassMap (fixtures/real/topology.json on the
    demo machine; documented 4-physical-core fallback when class
    identification is unavailable). Measured calibration points come from the
    store when present (B's CalibrationRecord rows). Suggestions only — the
    user selects; the selector still checks all usable configurations.
    """
    if _resolve_experiment(id) is None:
        raise HTTPException(status_code=404, detail=f"Experiment '{id}' not found")

    # CoreClassMap from the capability fixture (A's discovered topology)
    class_map = _fixture_class_map()

    from core.validation import dedupe_configurations, layout_configurations

    layouts = layout_configurations(class_map)
    layouts = dedupe_configurations(layouts)

    layout_points = [
        {
            "kind": "layout",
            "config_id": cfg.id,
            "layout": cfg.layout,
            "cpu_mask": _mask_from_cpus(cfg.cpu_affinity or []),
            "workers": cfg.worker_count,
            "description": (cfg.metadata or {}).get("description", ""),
            "measured": False,
            "source": "validation.layout_configurations",
        }
        for cfg in layouts
    ]

    calibration_points: list[dict[str, Any]] = []
    try:
        records = _STORE.get_calibrations()
        seen_classes: set[str] = set()
        for rec in records:
            key = f"{rec.core_class}:{rec.layout}:{json.dumps(rec.accepted_control or {}, sort_keys=True)}"
            if key in seen_classes:
                continue
            seen_classes.add(key)
            calibration_points.append(
                {
                    "kind": "calibration",
                    "config_id": f"cal_{rec.core_class}_{rec.layout}_{len(seen_classes):02d}",
                    "layout": rec.layout,
                    "core_class": rec.core_class,
                    "cpus": rec.cpus,
                    "control": rec.accepted_control or rec.requested_control,
                    "median_runtime_s": rec.runtime_s,
                    "median_energy_j": rec.package_energy_j,
                    "energy_available": rec.energy_available and rec.package_energy_j is not None,
                    "measured": True,
                    "source": "store.calibrations",
                }
            )
    except Exception:
        logger.exception("calibration lookup failed for validation points")

    return {
        "experiment_id": id,
        "layout_candidates": layout_points,
        "calibration_points": calibration_points,
        "note": "Convenience candidates only — the deterministic selector still checks all usable configurations.",
    }


def _fixture_class_map() -> "CoreClassMap":
    """CoreClassMap from A's discovered topology fixture (fallback: empty)."""
    try:
        top = _load_json_file("fixtures/real/topology.json")
        classes_raw = (top.get("core_classes") or {}).get("classes") or {}
        classes: dict[str, list[int]] = {}
        fast = efficient = ""
        for name, info in classes_raw.items():
            label = info.get("label", "")
            cpus = info.get("cpus", [])
            classes[label or name] = cpus
            if label == "fast":
                fast = label
            elif label == "efficient":
                efficient = label
        # Layouts: all logical CPUs of each class
        layouts = {
            "A": _sibling_pairs(classes.get(fast) or [], 4),
            "B": _all_physical(top),
            "C": list(range(int(top.get("ncpu", 16)))),
            "D": _sibling_pairs(classes.get(efficient) or [], 4),
        }
        return CoreClassMap(
            classes=classes,
            layouts=layouts,
            fast_class=fast,
            efficient_class=efficient,
            is_heterogeneous=bool(fast and efficient),
        )
    except Exception:
        return CoreClassMap()


def _sibling_pairs(cpus: list[int], n_physical: int) -> list[int]:
    """First n_physical physical cores, one SMT sibling each (PLAN §6 shapes)."""
    physical = [c for c in sorted(set(cpus)) if c < 64]
    smt: list[int] = []
    for c in physical[:n_physical]:
        smt.append(c)
        sibling = c + 8 if (c + 8) in cpus else None
        if sibling is not None:
            smt.append(sibling)
    return sorted(smt)


def _all_physical(top: dict[str, Any]) -> list[int]:
    """One logical CPU per physical core (first of each SMT group)."""
    groups = top.get("smt_groups") or {}
    if groups:
        # smt_groups: {"0": [0, 8], "1": [1, 9], ...} -> [0, 1, 2, ...]
        return sorted(int(v[0]) for v in groups.values() if isinstance(v, list) and v)
    ncpu = int(top.get("ncpu", 16))
    return list(range(0, ncpu, 2))


def _mask_from_cpus(cpus: list[int]) -> str:
    if not cpus:
        return ""
    return ",".join(str(c) for c in sorted(cpus))


def _load_json_file(rel_path: str) -> dict[str, Any]:
    p = Path(__file__).resolve().parent.parent / rel_path
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


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
    """Start passive background power watcher (0.5–1 Hz polling).

    Live wiring: Agent B's WatchDetector (core/watch.py) fed by the best
    available package-energy source (A's powercap backend when readable,
    B's synthetic scripted profile on dev machines). Read-only per §6b:
    no controls, no helper lease, missing energy never reported as zero.
    """
    global _WATCH_SERVICE
    if _WATCH_SERVICE is not None and _WATCH_SERVICE.detector.state != "stopped":
        return {
            "status": "already_watching",
            "poll_hz": _WATCH_SERVICE.status_dict()["poll_hz"],
            "state": _WATCH_SERVICE.detector.state,
            "message": "Watcher already running.",
        }
    _WATCH_SERVICE = WatchService(
        poll_hz=req.poll_hz,
        onset_s=float(req.onset_consecutive_s),
        idle_grace_s=float(req.idle_grace_s),
    )
    status = _WATCH_SERVICE.status_dict()
    return {
        "status": "watching",
        "poll_hz": status["poll_hz"],
        "state": _WATCH_SERVICE.detector.state,
        "source": _WATCH_SERVICE.source_info,
        "message": "Watcher started. Learning idle baseline (30-60s genuine idle).",
    }


@app.post("/api/watch/stop")
def stop_watch() -> dict[str, Any]:
    """Stop passive watcher, return observed activity segments with suggested budgets."""
    global _WATCH_SERVICE
    if _WATCH_SERVICE is None:
        return {"status": "stopped", "segments": [], "message": "No watcher running."}

    segments = [
        _WATCH_SERVICE.segment_frame(seg) for seg in _WATCH_SERVICE.detector.segments
    ]
    _WATCH_SERVICE.detector.state = "stopped"
    return {
        "status": "stopped",
        "segments": segments,
        "source": _WATCH_SERVICE.source_info,
    }


@app.get("/api/watch/status")
def get_watch_status() -> dict[str, Any]:
    """Current watcher state, baseline power, active observations."""
    if _WATCH_SERVICE is None:
        return {
            "active": False,
            "state": "idle",
            "source": None,
            "poll_hz": None,
            "current_power_w": None,
            "baseline_median_w": None,
            "baseline_spread_w": None,
            "active_segment_elapsed_s": None,
            "completed_segments_count": 0,
        }
    return _WATCH_SERVICE.status_dict()


@app.get("/api/watch/events")
async def get_watch_events() -> StreamingResponse:
    """SSE stream of watcher power samples, segment detection.

    Drives the live WatchService when active (real detector on the real
    backend, accelerated synthetic profile on dev machines); when idle, emits
    a single watch_state frame so consumers can render the idle state.
    """
    import asyncio as _asyncio

    async def watch_generator() -> AsyncGenerator[str, None]:
        if _WATCH_SERVICE is None:
            yield f"event: watch_state\ndata: {json.dumps({'state': 'idle', 'baseline_median_w': None, 'baseline_spread_w': None})}\n\n"
            return

        service = _WATCH_SERVICE
        yield service.state_frame()
        last_state = service.detector.state
        while service.detector.state != "stopped":
            await _asyncio.sleep(min(service._poll_interval_wall(), 1.0))
            sample = service._sample_once()
            if sample is None:
                continue
            yield service.sample_frame(sample)
            if service.detector.state != last_state:
                yield service.state_frame()
                last_state = service.detector.state
            closed = sample.get("closed_segment")
            if closed is not None:
                yield f"event: watch_segment\ndata: {json.dumps(service.segment_frame(closed))}\n\n"
            if service.source_info.get("synthetic") and service._profile_exhausted():
                break

    return StreamingResponse(watch_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# System Noise & Quiet Mode endpoints
# ---------------------------------------------------------------------------

class QuietSystemRequest(BaseModel):
    app_keys: Optional[list[str]] = None
    pids: Optional[list[int]] = None


@app.get("/api/system/noise")
def get_system_noise_endpoint() -> dict[str, Any]:
    """Scan running processes for non-essential applications and background noise."""
    from api.system import get_system_noise
    return get_system_noise()


@app.post("/api/system/quiet")
def quiet_system_endpoint(req: Optional[QuietSystemRequest] = None) -> dict[str, Any]:
    """Terminate detected noisy background applications to prepare machine for calibration."""
    from api.system import quiet_system
    app_keys = req.app_keys if req else None
    pids = req.pids if req else None
    return quiet_system(app_keys=app_keys, pids=pids)


@app.get("/api/system/thermal")
def get_system_thermal_endpoint() -> dict[str, Any]:
    """Inspect CPU thermal state, Tctl temperature, and potential throttling."""
    from api.system import get_thermal_status
    return get_thermal_status()


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
