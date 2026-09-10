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
