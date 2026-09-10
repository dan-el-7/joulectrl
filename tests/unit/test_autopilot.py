"""Unit tests for System-Wide Auto-Pilot mode."""

import pytest
from starlette.testclient import TestClient

from api.app import app
import api.app as app_module
from energy.synthetic import SyntheticEnergyBackend
from api.live import WatchService


@pytest.fixture
def client():
    return TestClient(app)


def test_autopilot_status_initially_stopped(client):
    """When no watcher is running, autopilot status reports disabled."""
    # Ensure any prior state is cleared
    client.post("/api/autopilot/disarm")
    res = client.get("/api/autopilot/status")
    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is False
    assert data["state"] == "stopped"


def test_autopilot_arm_and_disarm(client):
    """Arming autopilot enables background monitoring at stock boost."""
    # Arm autopilot in efficiency mode
    arm_res = client.post("/api/autopilot/arm", json={"objective": "efficiency", "onset_s": 2.0, "idle_grace_s": 3.0})
    assert arm_res.status_code == 200
    arm_data = arm_res.json()
    assert arm_data["ok"] is True
    assert arm_data["status"] == "armed"
    assert arm_data["objective"] == "efficiency"

    # Status should now report enabled
    st_res = client.get("/api/autopilot/status")
    assert st_res.status_code == 200
    st_data = st_res.json()
    assert st_data["enabled"] is True
    assert st_data["objective"] == "efficiency"
    assert st_data["control_state"] in ("stock_idle", "calibrating")

    # Disarm
    disarm_res = client.post("/api/autopilot/disarm")
    assert disarm_res.status_code == 200
    disarm_data = disarm_res.json()
    assert disarm_data["ok"] is True
    assert disarm_data["status"] == "disarmed"

    # Status returns to disabled
    st_res2 = client.get("/api/autopilot/status")
    assert st_res2.status_code == 200
    assert st_res2.json()["enabled"] is False


def test_autopilot_synthetic_workload_lifecycle():
    """Auto-Pilot lifecycle on a synthetic profile: detects spike -> clamps -> restores at idle."""
    backend = SyntheticEnergyBackend()
    backend.setup_standard_watch_profile()

    service = WatchService(
        poll_hz=1.0,
        onset_s=2.0,
        idle_grace_s=3.0,
        backend=backend,
        time_scale=1.0,
        active_control=True,
        optimization_objective="efficiency",
        recurrence_mode="repeated",
        initial_baseline_w=10.0,
    )
    app_module._WATCH_SERVICE = service

    try:
        # Initially at stock_idle
        assert service.control_state == "stock_idle"

        # Step through samples until spike triggers clamp
        active_seen = False
        restored_seen = False

        for _ in range(120):
            sample = service._sample_once()
            if service.control_state == "optimized_active":
                active_seen = True
            if active_seen and service.control_state == "stock_idle":
                restored_seen = True
                break

        assert active_seen, "Auto-pilot must transition to optimized_active during heavy workload"
        assert restored_seen, "Auto-pilot must return to stock_idle after workload returns to idle"
        assert service.active_sessions_count >= 1, "Must have recorded at least 1 savings session"
        assert service.total_saved_energy_j > 0, "Must have logged positive energy savings"
    finally:
        service.disarm()


def test_autopilot_curve_options(client):
    """GET /api/autopilot/curve-options returns available calibration curves with frontier points."""
    res = client.get("/api/autopilot/curve-options")
    assert res.status_code == 200
    data = res.json()
    assert "curves" in data
    assert len(data["curves"]) > 0

    first = data["curves"][0]
    assert "experiment_id" in first
    assert "workload_id" in first
    assert "baseline" in first
    assert "frontier_points" in first
    assert len(first["frontier_points"]) >= 1

    fp = first["frontier_points"][0]
    assert "config_id" in fp
    assert "energy_reduction_pct" in fp
    assert "runtime_increase_pct" in fp
    assert "median_runtime_s" in fp
    assert "median_energy_j" in fp


def test_autopilot_arm_with_target_savings(client):
    """Arming Auto-Pilot with a target savings percentage selects Pareto-optimal configuration."""
    # Disarm first
    client.post("/api/autopilot/disarm")

    # Arm with target 25%
    arm_res = client.post("/api/autopilot/arm", json={
        "objective": "custom_curve",
        "target_savings_pct": 25.0,
    })
    assert arm_res.status_code == 200
    arm_data = arm_res.json()
    assert arm_data["ok"] is True
    assert arm_data["status"] == "armed"
    assert arm_data["target_savings_pct"] == 25.0
    assert arm_data["curve_config_id"] is not None
    assert arm_data["empirical_savings_pct"] is not None

    # Inspect status
    st_res = client.get("/api/autopilot/status")
    assert st_res.status_code == 200
    st_data = st_res.json()
    assert st_data["enabled"] is True
    assert st_data["target_savings_pct"] == 25.0
    assert st_data["curve_config_id"] == arm_data["curve_config_id"]
    assert abs(st_data["empirical_savings_pct"] - arm_data["empirical_savings_pct"]) < 0.05
    assert st_data["empirical_runtime_penalty_pct"] is not None

    client.post("/api/autopilot/disarm")


def test_autopilot_curve_calibrated_energy_math():
    """Verify that WatchService uses exact empirical (T, E) ratios from calibration curve."""
    backend = SyntheticEnergyBackend()
    backend.setup_standard_watch_profile()

    # Suppose baseline was 100 J in 5s (20 W) and config was 60 J in 6s (10 W) -> 40% empirical energy reduction
    service = WatchService(
        poll_hz=1.0,
        onset_s=2.0,
        idle_grace_s=3.0,
        backend=backend,
        time_scale=1.0,
        active_control=True,
        optimization_objective="custom_curve",
        recurrence_mode="once",
        initial_baseline_w=10.0,
        target_savings_pct=35.0,
        curve_baseline_energy_j=100.0,
        curve_baseline_runtime_s=5.0,
        curve_config_energy_j=60.0,
        curve_config_runtime_s=6.0,
        curve_config_id="cfg_test_pareto",
    )
    app_module._WATCH_SERVICE = service

    try:
        # Simulate active segment close
        active_seen = False
        for _ in range(120):
            sample = service._sample_once()
            if service.control_state == "optimized_active":
                active_seen = True
            if active_seen and service.active_sessions_count > 0:
                break

        assert service.active_sessions_count == 1
        receipt = service.savings_history[-1]
        assert receipt["saved_pct"] == 40.0
        # Ratio stock to config is 100/60 = 1.6667
        # Estimated stock energy must equal actual_energy * (100 / 60)
        actual = receipt["actual_energy_j"]
        est_stock = receipt["estimated_stock_j"]
        expected_stock = round(actual * (100.0 / 60.0), 1)
        assert abs(est_stock - expected_stock) <= 0.2
        assert abs(receipt["saved_energy_j"] - (est_stock - actual)) <= 0.2
    finally:
        service.disarm()

