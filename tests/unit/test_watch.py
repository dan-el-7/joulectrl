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

