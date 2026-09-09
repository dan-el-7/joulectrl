"""Scripted power-profile tests for passive watch detection."""

from energy.synthetic import SyntheticEnergyBackend
from core.watch import WatchDetector


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
