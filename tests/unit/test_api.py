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
    assert res.json()["status"] == "watching"

    # Status
    res_st = client.get("/api/watch/status")
    assert res_st.status_code == 200
    assert res_st.json()["active"] is True

    # Stop watch
    res_stop = client.post("/api/watch/stop")
    assert res_stop.status_code == 200
    data = res_stop.json()
    assert data["status"] == "stopped"
    assert len(data["segments"]) == 1
    assert data["segments"][0]["mode"] == "watch"
    assert data["segments"][0]["duration_s"] > 0


def test_root_serves_frontend_or_fallback(client):
    res = client.get("/")
    assert res.status_code == 200
    # In dev with built dist, serves HTML; in pure CI without dist, serves JSON landing
    content_type = res.headers.get("content-type", "")
    if "text/html" in content_type:
        assert "joulectrl" in res.text
    else:
        assert res.json().get("name") == "joulectrl API"
