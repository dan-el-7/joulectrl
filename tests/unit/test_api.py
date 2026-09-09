"""tests/unit/test_api.py — Unit tests for joulectrl FastAPI application (Agent C)."""

import json
import pytest
from fastapi.testclient import TestClient

from api.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_capabilities(client):
    res = client.get("/api/capabilities")
    assert res.status_code == 200
    data = res.json()
    assert "machine" in data
    assert "topology" in data
    assert "energy" in data
    assert data["energy"]["available"] is True
    assert "package-0" in data["energy"]["domain"]
    assert "controls" in data
    assert data["restoration"]["status"] == "restored"


def test_workloads(client):
    res = client.get("/api/workloads")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    ids = [w["id"] for w in data]
    assert "clean_build" in ids


def test_list_and_get_experiment(client):
    res = client.get("/api/experiments")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 1
    exp_id = data[0]["id"]

    res2 = client.get(f"/api/experiments/{exp_id}")
    assert res2.status_code == 200
    exp = res2.json()
    assert exp["id"] == exp_id
    assert "profile" in exp
    assert "configurations" in exp["profile"]
    assert len(exp["profile"]["configurations"]) == 12
    assert "selection" in exp
    assert "validation" in exp
    assert exp["restoration_status"] == "restored"


def test_create_experiment(client):
    payload = {
        "workload_id": "clean_build",
        "objective": "deadline",
        "runtime_budget_s": 40.0,
    }
    res = client.post("/api/experiments", json=payload)
    assert res.status_code == 201
    created = res.json()
    assert "id" in created
    assert created["workload_id"] == "clean_build"
    assert created["runtime_budget_s"] == 40.0


def test_select_deadline(client):
    exp_id = "exp_demo_clean_build"
    payload = {
        "objective": "deadline",
        "runtime_budget_s": 46.0,
        "headroom_pct": 5.0,
    }
    res = client.post(f"/api/experiments/{exp_id}/select", json=payload)
    assert res.status_code == 200
    sel = res.json()
    assert sel["objective"] == "deadline"
    assert "config_id" in sel
    assert "metrics" in sel


def test_select_preference_mode(client):
    exp_id = "exp_demo_clean_build"
    payload = {
        "objective": "preference",
        "preference": {
            "energy_target_pct": 70.0,
            "perf_floor_pct": 60.0,
        },
        "headroom_pct": 5.0,
    }
    res = client.post(f"/api/experiments/{exp_id}/select", json=payload)
    assert res.status_code == 200
    sel = res.json()
    assert sel["objective"] == "preference"
    assert sel["preference_outcomes"]["energy_target_met"] is True


def test_validate(client):
    res = client.post("/api/experiments/exp_demo_clean_build/validate")
    assert res.status_code == 202
    assert res.json()["status"] == "validation_started"


def test_cancel(client):
    res = client.post("/api/experiments/exp_demo_clean_build/cancel")
    assert res.status_code == 200
    assert res.json()["status"] == "cancelling"


def test_restore(client):
    res = client.post("/api/restore")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "restored"
    assert data["verified"] is True


def test_explain(client):
    res = client.post("/api/explain", json={"experiment_id": "exp_demo_clean_build", "provider": "template"})
    assert res.status_code == 200
    data = res.json()
    assert "text" in data
    assert "grounding_facts" in data
    assert len(data["grounding_facts"]) >= 1


def test_export(client):
    res = client.get("/api/experiments/exp_demo_clean_build/export")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "exp_demo_clean_build"


def test_watch_lifecycle(client):
    # Start watch
    res = client.post("/api/watch/start", json={"poll_hz": 1.0})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "watching"
    assert "source" in body  # real powercap or synthetic — always labeled
    assert body["state"] == "calibrating"

    # Status
    res_st = client.get("/api/watch/status")
    assert res_st.status_code == 200
    assert res_st.json()["active"] is True
    assert res_st.json()["poll_hz"] == 1.0

    # Stop watch before any segment closes (immediate stop) — no invented data
    res_stop = client.post("/api/watch/stop")
    assert res_stop.status_code == 200
    data = res_stop.json()
    assert data["status"] == "stopped"
    assert isinstance(data["segments"], list)  # empty until a segment actually closed
    for seg in data["segments"]:
        assert seg["mode"] == "watch"
        assert seg["duration_s"] > 0
        # honesty guards: missing energy is never zero
        if not seg["energy_available"]:
            assert seg["estimated_energy_j"] is None

    # Stopping again without a session is a clean no-op
    res_stop2 = client.post("/api/watch/stop")
    assert res_stop2.status_code == 200
    assert res_stop2.json()["status"] == "stopped"


def test_watch_detector_closes_segment_on_scripted_profile():
    """Live wiring: B's WatchDetector fed the full scripted idle→activity→idle
    profile (with mid-task dip) must close exactly one segment with honest
    energy and a suggested budget (§6b: dip absorbed, settle time excluded)."""
    from energy.synthetic import SyntheticEnergyBackend

    from api.live import WatchService

    backend = SyntheticEnergyBackend()
    backend.setup_standard_watch_profile()
    service = WatchService(
        poll_hz=1.0, onset_s=3.0, idle_grace_s=10.0, backend=backend, time_scale=1.0
    )

    frames = []
    for _ in range(130):  # scripted profile is 120 s at 1 Hz
        sample = service._sample_once()
        if sample is None:
            continue
        frames.append(sample)
        if sample.get("closed_segment") is not None:
            break

    closed = [f for f in frames if f.get("closed_segment")]
    assert len(closed) == 1, "mid-task dip must not close the segment early"
    seg = service.segment_frame(closed[0]["closed_segment"])
    assert seg["mode"] == "watch"
    assert seg["duration_s"] > 0
    # Task window: 20s + 6s dip + 24s = ~44-50 s of activity, minus boundary
    # samples; runtime must be in a sane band (not the full 120 s profile).
    assert 30.0 < seg["duration_s"] < 70.0, f"unexpected runtime {seg['duration_s']}"
    assert seg["estimated_energy_j"] is not None and seg["estimated_energy_j"] > 0
    assert seg["suggested_budget_s"] >= seg["duration_s"]
    assert "Uncertainty" in seg["note"]


def test_watch_status_idle_when_never_started():
    import api.app as app_module
    from fastapi.testclient import TestClient

    prev = app_module._WATCH_SERVICE
    app_module._WATCH_SERVICE = None  # reset module state from earlier tests
    try:
        with TestClient(app_module.app) as fresh_client:
            res = fresh_client.get("/api/watch/status")
            assert res.status_code == 200
            body = res.json()
            assert body["active"] is False
            assert body["state"] == "idle"
            assert body["completed_segments_count"] == 0
    finally:
        app_module._WATCH_SERVICE = prev


def test_select_publishes_selection_updated_on_bus(client):
    """POST /select must publish selection_updated on B's EventBus (AFFECTS(c))."""
    from core.events import default_bus

    received = []
    evlog = default_bus().for_experiment(SYNTHETIC_ID)
    unsub = evlog.subscribe(lambda e: received.append(e))

    res = client.post(
        f"/api/experiments/{SYNTHETIC_ID}/select",
        json={"objective": "deadline", "runtime_budget_s": 50.0},
    )
    assert res.status_code == 200
    unsub()

    events = [e for e in received if e.name == "selection_updated"]
    assert events, "selection_updated must be published on the bus"
    assert events[0].payload["selection"]["objective"] == "deadline"


def test_sse_replays_live_bus_history():
    """The SSE frame source must replay B's bus history for an experiment
    (replay(0) burst) using B's authoritative sse_frame format.

    Note: tested at the generator level because this TestClient/httpx stack
    buffers infinite SSE responses (verified: iter_lines/iter_bytes block
    until stream end on any infinite StreamingResponse). The HTTP endpoint is
    a thin wrapper: it runs this exact generator; live TCP verification runs
    in the C#3 session smoke (see HANDOFF).
    """
    import asyncio

    from api.live import stream_experiment_events
    from core.events import default_bus

    bus = default_bus()
    bus.publish(
        SYNTHETIC_ID,
        "experiment_state",
        {"experiment_id": SYNTHETIC_ID, "state": "PROFILING", "previous_state": "PREPARING"},
    )
    bus.publish(
        SYNTHETIC_ID,
        "run_progress",
        {"experiment_id": SYNTHETIC_ID, "phase": "profiling", "status": "running"},
    )

    async def collect():
        agen = stream_experiment_events(SYNTHETIC_ID, keepalive_s=0.1)
        frames = []

        async def read():
            async for frame in agen:
                frames.append(frame)
                # Bus history may carry events from earlier tests on the same
                # experiment id — read until the run_progress replay lands.
                if "event: run_progress" in frame:
                    return

        try:
            await asyncio.wait_for(read(), timeout=3)
        finally:
            await agen.aclose()
        return frames

    frames = asyncio.run(collect())
    text = "".join(frames)
    assert "event: experiment_state" in text
    assert "PROFILING" in text
    assert "event: run_progress" in text
    # B's sse_frame format is authoritative
    assert 'data: {"experiment_id"' in text


def test_sse_live_follow_publishes_after_replay():
    """After the replay burst, a newly published bus event must be delivered
    by the live-follow loop (proves subscribe wiring, not just replay)."""
    import asyncio

    from api.live import stream_experiment_events
    from core.events import default_bus

    exp_id = "exp_sse_live_follow_test"
    bus = default_bus()
    bus.publish(exp_id, "experiment_state", {"experiment_id": exp_id, "state": "PREPARING"})

    async def collect():
        evlog = default_bus().for_experiment(exp_id)
        agen = stream_experiment_events(exp_id, keepalive_s=0.2)
        frames = []

        async def read():
            async for frame in agen:
                frames.append(frame)
                # First frame = replay; then publish a live event mid-stream.
                if len(frames) == 1:
                    evlog.publish(
                        "run_complete",
                        {"experiment_id": exp_id, "phase": "profiling", "status": "success"},
                    )
                if len(frames) >= 2:
                    return

        try:
            await asyncio.wait_for(read(), timeout=5)
        finally:
            await agen.aclose()
        return frames

    frames = asyncio.run(collect())
    assert len(frames) >= 2
    assert "event: experiment_state" in frames[0]
    live = frames[1]
    assert "event: run_complete" in live and "success" in live


def test_validation_points_endpoint(client):
    """Validation-point candidates: B's layouts + measured calibration points."""
    res = client.get(f"/api/experiments/{SYNTHETIC_ID}/validation-points")
    assert res.status_code == 200
    body = res.json()
    kinds = {p["kind"] for p in body["layout_candidates"]}
    assert kinds == {"layout"}
    ids = [p["config_id"] for p in body["layout_candidates"]]
    assert "layout_B_all_physical" in ids
    assert "layout_C_all_logical" in ids
    for p in body["layout_candidates"]:
        assert p["cpu_mask"], "layout candidates must carry a cpu mask"
        assert p["measured"] is False
    for p in body["calibration_points"]:
        assert p["measured"] is True
        if not p["energy_available"]:
            assert p["median_energy_j"] is None


def test_root_serves_frontend_or_fallback(client):
    res = client.get("/")
    assert res.status_code == 200
    # In dev with built dist, serves HTML; in pure CI without dist, serves JSON landing
    content_type = res.headers.get("content-type", "")
    if "text/html" in content_type:
        assert "joulectrl" in res.text
    else:
        assert res.json().get("name") == "joulectrl API"


# ---------------------------------------------------------------------------
# Store-backed integration (Agent B's Store + Agent D's synthetic fixtures)
# ---------------------------------------------------------------------------

SYNTHETIC_ID = "exp_synthetic_clean_build_001"


def test_store_seeded_experiments_listed(client):
    res = client.get("/api/experiments")
    assert res.status_code == 200
    ids = [e["id"] for e in res.json()]
    assert "exp_demo_clean_build" in ids
    assert SYNTHETIC_ID in ids


def test_synthetic_experiment_served_end_to_end(client):
    res = client.get(f"/api/experiments/{SYNTHETIC_ID}")
    assert res.status_code == 200
    exp = res.json()
    assert exp["state"] == "COMPLETE"
    assert len(exp["profile"]["configurations"]) >= 1
    assert exp["profile"]["runs"], "profiling runs must come from the persisted store"
    sel = exp["selection"]
    assert sel["config_id"] == sel["selected_config_id"]
    assert sel["objective"] == "deadline"
    assert "metrics" in sel
    assert exp["validation"]["status"] == "verified"
    assert exp["validation"]["verified_savings_pct"] is not None
    assert exp["restoration_status"] in {"restored", "not_required"}
    assert exp["state_transitions"], "state-machine history must be visible"


def test_select_uses_optimizer_and_persists(client):
    res = client.post(
        f"/api/experiments/{SYNTHETIC_ID}/select",
        json={"objective": "deadline", "runtime_budget_s": 45.0, "headroom_pct": 5.0},
    )
    assert res.status_code == 200
    sel = res.json()
    assert sel["objective"] == "deadline"
    assert sel["config_id"]
    # Persisted: a re-read of the experiment reflects the same selection
    exp = client.get(f"/api/experiments/{SYNTHETIC_ID}").json()
    assert exp["selection"]["config_id"] == sel["config_id"]


def test_select_preference_requires_targets(client):
    res = client.post(
        f"/api/experiments/{SYNTHETIC_ID}/select",
        json={"objective": "preference"},
    )
    assert res.status_code == 400


def test_explain_uses_deterministic_templates(client):
    res = client.post(
        "/api/explain",
        json={"experiment_id": SYNTHETIC_ID, "provider": "template"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["provider_effective"] == "template"
    assert data["fallback"] is False
    # Deterministic template output quotes measured numbers, not hardcoded strings
    assert "median package energy" in data["text"]
    assert len(data["grounding_facts"]) >= 3


def test_explain_llm_provider_degrades_to_basic(client):
    res = client.post(
        "/api/explain",
        json={"experiment_id": SYNTHETIC_ID, "provider": "local_llm"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["provider"] == "local_llm"
    assert data["provider_effective"] == "template"
    assert data["fallback"] is True
    assert "median package energy" in data["text"]


def test_restore_records_persisted_status(client):
    res = client.post("/api/restore", json={"experiment_id": SYNTHETIC_ID})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "restored"
    assert data["verified"] is True
    exp = client.get(f"/api/experiments/{SYNTHETIC_ID}").json()
    assert exp["restoration_status"] == "restored"


def test_cancel_records_restoration(client):
    res = client.post(f"/api/experiments/{SYNTHETIC_ID}/cancel")
    assert res.status_code == 200
    assert res.json()["status"] == "cancelling"
    exp = client.get(f"/api/experiments/{SYNTHETIC_ID}").json()
    assert exp["state"] == "RESTORED"
    assert exp["restoration_status"] == "restored"


def test_export_from_store(client):
    res = client.get(f"/api/experiments/{SYNTHETIC_ID}/export")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == SYNTHETIC_ID
    assert data["runs"], "export must include raw run records for auditability"


def test_bisection_candidate_generation():
    from api.engine import LiveEngine
    engine = LiveEngine(bus=None, store_bridge_mod=None)
    cls_map = {
        "fast": {"cpus": [0, 2, 4, 6], "hw_max_freq": 5090910},
        "efficient": {"cpus": [1, 3, 5, 7], "hw_max_freq": 3506494},
    }
    configs = engine._candidate_configs(cls_map, passive=True)
    assert len(configs) >= 50, "Should generate a rich multi-resolution ladder"

    # Verify order: Round 0 anchors (stock max and min cap) come first
    first_cids = [c[0].id for c in configs[:6]]
    assert "cfg_all_physical_stock" in first_cids
    assert "cfg_all_physical_cap623m" in first_cids
    assert "cfg_fast_class_stock" in first_cids
    assert "cfg_fast_class_cap623m" in first_cids

    # Verify Round 1 midpoint (50% cap ~1.31 GHz) comes next
    mid_cids = [c[0].id for c in configs[6:12]]
    assert any("cap1311m" in cid for cid in mid_cids)

    # Verify all configs are unique
    keys = [(tuple(c[0].cpu_affinity or []), c[0].boost, c[0].freq_cap_khz, c[0].worker_count) for c in configs]
    assert len(keys) == len(set(keys)), "Every candidate configuration must be unique"


def test_create_experiment_with_repetitions(client):
    payload = {
        "workload_id": "fixed_compute",
        "objective": "preference",
        "repetitions": 2,
    }
    res = client.post("/api/experiments", json=payload)
    assert res.status_code == 201
    created = res.json()
    assert "id" in created


def test_engine_profile_rows_repetition_aggregation():
    from api.engine import LiveEngine
    from core.models import Configuration, RunRecord

    engine = LiveEngine(bus=None, store_bridge_mod=None)
    cls_map = {"class_0": {"cpus": [0, 1], "hw_max_freq": 2000000}}

    cfg = Configuration(id="cfg_test", layout="B", worker_count=2, cpu_affinity=[0, 1], freq_cap_khz=2000000, boost=True)

    rec1 = RunRecord(
        run_id="run_1", experiment_id="exp_test", config_id=cfg.id,
        workload_name="fixed_compute", repetition=1, phase="profiling",
        configuration=cfg, runtime_s=2.0, package_energy_j=10.0, energy_available=True,
        status="success",
    )
    rec2 = RunRecord(
        run_id="run_2", experiment_id="exp_test", config_id=cfg.id,
        workload_name="fixed_compute", repetition=2, phase="profiling",
        configuration=cfg, runtime_s=2.2, package_energy_j=11.0, energy_available=True,
        status="success",
    )

    rows = engine._profile_rows(cal=None, runs=[rec1, rec2], cls_map=cls_map, workload_id="fixed_compute")
    assert len(rows) == 1
    row = rows[0]
    assert row["runtimes"] == [2.0, 2.2]
    assert row["energies"] == [10.0, 11.0]
    assert row["median_runtime_s"] == 2.1
    assert row["median_energy_j"] == 10.5


def test_system_noise_endpoint(client):
    res = client.get("/api/system/noise")
    assert res.status_code == 200
    data = res.json()
    assert "is_quiet" in data
    assert "total_noise_cpu_pct" in data
    assert "detected_apps" in data
    assert "unclassified_processes" in data
    # Ensure protected apps are not in detected_apps
    detected_keys = [app["key"] for app in data["detected_apps"]]
    assert "antigravity" not in detected_keys
    assert "uvicorn" not in detected_keys


def test_system_quiet_endpoint(client):
    # Call quiet with empty/non-existent app key to verify endpoint contract safely
    res = client.post("/api/system/quiet", json={"app_keys": ["non_existent_app_xyz"]})
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "terminated_pids" in data
    assert "closed_apps" in data
    assert "remaining_noise" in data


def test_calibration_endpoint_aggregates_store(client):
    res = client.get("/api/calibration")
    assert res.status_code == 200
    data = res.json()
    assert "classes" in data
    assert len(data["classes"]) >= 2
    # Verify points have score and averaging
    all_points = [p for c in data["classes"] for p in c["points"]]
    assert len(all_points) > 0
    for p in all_points:
        assert "watts" in p and p["watts"] > 0
        assert "score" in p and p["score"] > 0
        assert "runtime_s" in p and p["runtime_s"] > 0
        assert "n" in p and p["n"] >= 1
    # Check experiment filtering
    if data.get("experiments"):
        exp_id = data["experiments"][0]["id"]
        res_exp = client.get(f"/api/calibration?experiment_id={exp_id}")
        assert res_exp.status_code == 200
        assert res_exp.json()["current_experiment_id"] == exp_id


def test_system_processes_and_priority_endpoints(client):
    res = client.get("/api/system/processes")
    assert res.status_code == 200
    data = res.json()
    assert "processes" in data
    assert "total" in data

    # Test process priority with current pid
    import os
    pid = os.getpid()
    res_prio = client.post(
        "/api/system/process-priority",
        json={"pid": pid, "policy": "deprioritize_eco"},
    )
    assert res_prio.status_code == 200
    assert res_prio.json()["ok"] is True
    assert "Zen 5c" in res_prio.json()["affinity_label"] or "Eco" in res_prio.json()["affinity_label"]

    res_restore = client.post(
        "/api/system/process-priority",
        json={"pid": pid, "policy": "restore_normal"},
    )
    assert res_restore.status_code == 200
    assert res_restore.json()["ok"] is True


