"""Scripted power-profile tests for passive watch detection."""

from energy.synthetic import SyntheticEnergyBackend
from core.watch import WatchDetector, WatchSegment


def test_watch_backdates_onset_and_end_and_absorbs_dip():
    backend = SyntheticEnergyBackend()
    backend.setup_standard_watch_profile()
    detector = WatchDetector(energy_range_uj=backend.max_energy_range_uj, onset_s=3, idle_grace_s=10)
    closed = None
    for _ in range(120):
        uj, power, timestamp = backend.step(1.0)
        result = detector.observe(power, uj, timestamp)
        if result is not None:
            closed = result

    assert closed is not None
    assert closed.start_ts == 31.0
    assert closed.end_ts == 80.0
    assert closed.runtime_s == 49.0
    assert closed.energy_j is not None
    record = closed.to_run_record("watch-exp", "external-task")
    assert record.mode == "watch"
    assert record.watch_note == "estimated via idle-return detection"


def test_watch_missing_counter_never_becomes_zero():
    detector = WatchDetector(baseline_window_s=2, onset_s=1, idle_grace_s=2)
    detector.observe(10.0, None, 0.0)
    detector.observe(10.0, None, 1.0)
    detector.observe(50.0, None, 2.0)
    detector.observe(50.0, None, 3.0)
    detector.observe(50.0, None, 4.0)
    detector.observe(10.0, None, 5.0)
    result = detector.observe(10.0, None, 7.0)
    assert result is not None
    assert not result.energy_available
    assert result.energy_j is None


def test_watch_bursty_geekbench_absorbs_pauses_and_trims_tail():
    """Simulate a bursty multi-phase workload (like Geekbench):
    - Baseline idle at 10W (0-5s)
    - Phase 1 burst at 45W (5-10s)
    - Inter-test pause at 10W (10-16s, 6s gap)
    - Phase 2 burst at 55W (16-25s)
    - Inter-test pause at 10W (25-32s, 7s gap)
    - Phase 3 burst at 60W (32-40s)
    - Workload complete: sustained idle (40-60s)
    Verify:
    1. Pauses are absorbed into ONE segment.
    2. Start is exact first spike (t=5.0).
    3. End is exact last active spike (t=40.0).
    4. Runtime is 35.0s (40.0 - 5.0).
    5. The trailing 15s idle grace is trimmed away!
    """
    detector = WatchDetector(baseline_window_s=5, onset_s=2, idle_grace_s=15)
    closed = None
    uj = 1000000

    for t in range(60):
        # Determine power
        if 5 <= t <= 10:
            p = 45.0
        elif 16 <= t <= 25:
            p = 55.0
        elif 32 <= t <= 40:
            p = 60.0
        else:
            p = 10.0
        uj += int(p * 1e6)
        res = detector.observe(p, uj, float(t))
        if res is not None:
            closed = res

    assert closed is not None
    assert closed.start_ts == 5.0
    assert closed.end_ts == 40.0
    assert closed.runtime_s == 35.0


def test_watch_callbacks_on_active_and_idle():
    active_events = []
    idle_events = []

    def handle_active(ts: float, power_w: float):
        active_events.append((ts, power_w))

    def handle_idle(segment):
        idle_events.append(segment)

    detector = WatchDetector(
        baseline_window_s=2,
        onset_s=2,
        idle_grace_s=3,
        initial_baseline_w=10.0,
        on_active=handle_active,
        on_idle=handle_idle,
    )

    assert detector.state == "idle"
    assert detector.baseline_w == 10.0

    # Feed idle samples
    detector.observe(10.0, 1000000, 0.0)
    detector.observe(10.5, 2000000, 1.0)
    assert len(active_events) == 0

    # Start spike: 40W at t=2.0
    detector.observe(40.0, 3000000, 2.0)
    assert len(active_events) == 0  # onset_s is 2, need sustained spike

    # Sustained spike at t=4.0
    detector.observe(42.0, 4000000, 4.0)
    assert len(active_events) == 1
    assert active_events[0] == (4.0, 42.0)
    assert detector.state == "active"

    # Sustained spike continues
    detector.observe(41.0, 5000000, 5.0)
    assert len(active_events) == 1  # Not triggered again while active

    # Return to idle: 10W at t=6.0, t=7.0, t=8.0, t=9.0 (grace is 3s)
    detector.observe(10.0, 6000000, 6.0)
    detector.observe(10.0, 7000000, 7.0)
    detector.observe(10.0, 8000000, 8.0)
    assert len(idle_events) == 0
    seg = detector.observe(10.0, 9000000, 9.0)

    assert seg is not None
    assert len(idle_events) == 1
    assert idle_events[0].start_ts == 2.0
    assert idle_events[0].end_ts == 5.0


def test_watch_service_active_control_workflow():
    from unittest.mock import MagicMock
    from api.live import WatchService

    mock_helper = MagicMock()
    mock_helper.begin_session.return_value = {"ok": True}
    mock_helper.apply_configuration.return_value = {"ok": True}
    mock_helper.restore.return_value = {"ok": True}
    mock_helper.end_session.return_value = {"ok": True}

    service = WatchService(
        onset_s=2.0,
        idle_grace_s=3.0,
        initial_baseline_w=10.0,
        active_control=True,
        target_pid=99999,
        target_process_name="test_heavy_app",
    )
    service._helper = mock_helper

    assert service.control_state == "stock_idle"
    assert service.active_control is True

    # Simulate active spike
    service.detector.observe(45.0, 1000000, 0.0)
    service.detector.observe(45.0, 2000000, 2.0)

    assert service.control_state == "optimized_active"
    mock_helper.begin_session.assert_called_once()
    mock_helper.apply_configuration.assert_called_with({"boost": False})

    # Simulate idle return
    service.detector.observe(10.0, 3000000, 3.0)
    service.detector.observe(10.0, 4000000, 4.0)
    service.detector.observe(10.0, 5000000, 5.0)
    service.detector.observe(10.0, 6000000, 6.0)

    assert service.control_state == "stock_idle"
    mock_helper.restore.assert_called_once()
    mock_helper.end_session.assert_called_once()
    assert service.active_sessions_count == 1
    assert service.total_saved_energy_j > 0
    assert len(service.savings_history) == 1
    st = service.status_dict()
    assert st["active_control"] is True
    assert st["control_state"] == "stock_idle"
    assert st["target_pid"] == 99999
    assert st["optimization_objective"] == "efficiency"
    assert st["recurrence_mode"] == "repeated"


def test_watch_service_recurrence_once():
    from unittest.mock import MagicMock
    from api.live import WatchService

    mock_helper = MagicMock()
    service = WatchService(
        onset_s=1.0,
        idle_grace_s=2.0,
        initial_baseline_w=10.0,
        active_control=True,
        recurrence_mode="once",
    )
    service._helper = mock_helper

    # Spike
    service.detector.observe(45.0, 1000000, 0.0)
    service.detector.observe(45.0, 2000000, 1.5)
    assert service.control_state == "optimized_active"

    # Idle return -> should disarm and become "completed"
    service.detector.observe(10.0, 3000000, 2.0)
    service.detector.observe(10.0, 4000000, 3.0)
    service.detector.observe(10.0, 5000000, 4.5)

    assert service.control_state == "completed"
    assert service.active_control is False


def test_watch_service_performance_objective():
    from unittest.mock import MagicMock
    from api.live import WatchService

    mock_helper = MagicMock()
    service = WatchService(
        onset_s=1.0,
        idle_grace_s=2.0,
        initial_baseline_w=10.0,
        active_control=True,
        optimization_objective="performance",
    )
    service._helper = mock_helper

    # Spike
    service.detector.observe(45.0, 1000000, 0.0)
    service.detector.observe(45.0, 2000000, 1.5)
    assert service.control_state == "shielded_boost"
    # Should NOT throttle frequency
    mock_helper.apply_configuration.assert_not_called()


def test_watch_service_deadline_objective():
    from unittest.mock import MagicMock
    from api.live import WatchService

    mock_helper = MagicMock()
    service = WatchService(
        onset_s=1.0,
        idle_grace_s=2.0,
        initial_baseline_w=10.0,
        active_control=True,
        optimization_objective="deadline",
        time_budget_s=12.0,
    )
    service._helper = mock_helper

    # Spike
    service.detector.observe(45.0, 1000000, 0.0)
    service.detector.observe(45.0, 2000000, 1.5)
    assert service.control_state == "optimized_active"
    mock_helper.apply_configuration.assert_called_once()






class TestAdaptiveBaselineAndResetGuard:
    def _detector(self):
        return WatchDetector(initial_baseline_w=8.0, onset_s=2.0, idle_grace_s=6.0,
                             poll_interval_s=1.0, energy_range_uj=65_532_610_987)

    def test_baseline_adapts_to_idle_drift(self):
        d = self._detector()
        t = 0.0
        i = 0
        # Gradual drift 8W -> 18W in +2W steps, each inside the band vs the
        # rolling median, so samples keep adapting the baseline (never spiking).
        for w in (10.0, 12.0, 14.0, 16.0, 18.0):
            for _ in range(8):
                d.observe(w, None, t + i)
                i += 1
        # Threshold must now sit above 18W-ish band so 20W is NOT a spike,
        # while a genuine 35W spike still triggers onset.
        assert d.state == "idle"
        fired = []
        d.on_active = lambda ts, w: fired.append(ts)
        for i in range(40, 50):
            d.observe(35.0, None, t + i)
        assert fired, "spike must still be detected after baseline drift adaptation"

    def test_segment_energy_reset_returns_none(self):
        d = self._detector()
        # Close a segment whose counter delta implies >200W — must yield None.
        seg = WatchSegment(start_ts=0.0, end_ts=10.0, start_energy_uj=1000,
                           end_energy_uj=10_000_000_000, energy_range_uj=65_532_610_987,
                           baseline_w=8.0, spread_w=1.0, poll_interval_s=1.0)
        assert seg.energy_j is None
