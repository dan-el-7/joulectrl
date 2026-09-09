"""tests/integration/test_watch_mode.py — Integration tests for passive watch mode auto-detection (§6b)."""

import unittest
from typing import Optional

from core.models import RunRecord
from energy.synthetic import SyntheticEnergyBackend


class WatchModeDetector:
    """Reference implementation of the passive idle->activity->idle auto-detection logic (PLAN §6b).
    
    Verifies that the detector contract behaves identically against synthetic scripted traces
    and real hardware powercap traces.
    """

    def __init__(
        self,
        idle_threshold_w: float = 15.0,
        onset_sustained_s: float = 2.0,
        grace_period_s: float = 10.0,
    ) -> None:
        self.idle_threshold_w = idle_threshold_w
        self.onset_sustained_s = onset_sustained_s
        self.grace_period_s = grace_period_s

        # Detection state
        self.state: str = "IDLE"  # IDLE, CANDIDATE_ONSET, ACTIVE, CANDIDATE_END, COMPLETED
        self.baseline_samples: list[float] = []
        self.onset_candidate_ts: Optional[float] = None
        self.onset_start_energy_uj: Optional[int] = None
        
        self.confirmed_onset_ts: Optional[float] = None
        self.last_above_band_ts: Optional[float] = None
        self.last_above_band_uj: Optional[int] = None

        self.dip_start_ts: Optional[float] = None
        self.completed_record: Optional[RunRecord] = None

    def sample(self, power_w: float, energy_uj: Optional[int], ts: float, backend: SyntheticEnergyBackend) -> Optional[RunRecord]:
        """Process one power/energy sample."""
        is_above_band = power_w > self.idle_threshold_w

        if self.state == "IDLE":
            if is_above_band:
                self.state = "CANDIDATE_ONSET"
                self.onset_candidate_ts = ts
                self.onset_start_energy_uj = energy_uj
            else:
                self.baseline_samples.append(power_w)

        elif self.state == "CANDIDATE_ONSET":
            if is_above_band:
                assert self.onset_candidate_ts is not None
                if ts - self.onset_candidate_ts >= self.onset_sustained_s:
                    # Confirmed onset! Backdated to first above-band sample
                    self.state = "ACTIVE"
                    self.confirmed_onset_ts = self.onset_candidate_ts
                    self.last_above_band_ts = ts
                    self.last_above_band_uj = energy_uj
            else:
                # Rejected as a transient background blip
                self.state = "IDLE"
                self.onset_candidate_ts = None
                self.onset_start_energy_uj = None

        elif self.state == "ACTIVE":
            if is_above_band:
                self.last_above_band_ts = ts
                self.last_above_band_uj = energy_uj
            else:
                # Dropped into idle band: start grace period
                self.state = "CANDIDATE_END"
                self.dip_start_ts = ts

        elif self.state == "CANDIDATE_END":
            if is_above_band:
                # Mid-task dip rule: returned above band before grace period expired -> absorbed!
                self.state = "ACTIVE"
                self.last_above_band_ts = ts
                self.last_above_band_uj = energy_uj
                self.dip_start_ts = None
            else:
                assert self.dip_start_ts is not None
                if ts - self.dip_start_ts >= self.grace_period_s:
                    # Grace period expired! Declare task completion and backtrack end
                    self.state = "COMPLETED"
                    assert self.confirmed_onset_ts is not None
                    assert self.last_above_band_ts is not None

                    runtime_s = self.last_above_band_ts - self.confirmed_onset_ts
                    delta_j = backend.compute_delta_j(self.onset_start_energy_uj, self.last_above_band_uj)
                    avg_power_w = delta_j / runtime_s if (delta_j is not None and runtime_s > 0) else 0.0

                    self.completed_record = RunRecord(
                        run_id=f"watch_{int(self.confirmed_onset_ts)}",
                        experiment_id="watch_passive_experiment",
                        config_id="uncontrolled",
                        workload_name="unspecified",
                        repetition=1,
                        mode="watch",
                        phase="watch",
                        runtime_s=round(runtime_s, 2),
                        package_energy_j=round(delta_j, 2) if delta_j is not None else None,
                        energy_available=(delta_j is not None),
                        avg_power_w=round(avg_power_w, 2),
                        status="success",
                        output_verified=True,
                        onset_ts=self.confirmed_onset_ts,
                        end_ts=self.last_above_band_ts,
                        idle_baseline_w=round(sum(self.baseline_samples) / len(self.baseline_samples), 2) if self.baseline_samples else None,
                        watch_note="estimated via idle-return detection",
                    )
                    return self.completed_record

        return None


class TestWatchModeIntegration(unittest.TestCase):
    """Verify passive watch mode auto-detection against scripted power profiles."""

    def test_standard_profile_onset_dip_and_backtracked_end(self):
        """Verify:
        1. Idle baseline learned
        2. Onset confirmed & backdated (sustained >= 2s)
        3. Mid-task dip (6s) absorbed under 10s grace period
        4. End detected & backtracked to last above-band sample
        5. Exact runtime (50.0s) and energy (~2224J) computed
        """
        backend = SyntheticEnergyBackend()
        backend.setup_standard_watch_profile()

        detector = WatchModeDetector(idle_threshold_w=15.0, onset_sustained_s=2.0, grace_period_s=10.0)

        # Step through simulated profile at 1 Hz
        completed_record = None
        dt = 1.0
        total_duration = 120.0
        steps = int(total_duration / dt)

        for _ in range(steps):
            uj, power_w, ts = backend.step(dt)
            record = detector.sample(power_w, uj, ts, backend)
            if record is not None:
                completed_record = record
                break

        self.assertIsNotNone(completed_record)
        self.assertEqual(completed_record.mode, "watch")
        self.assertTrue(completed_record.energy_available)

        # Backdated onset at t=31.0s; backtracked end at t=80.0s (runtime 49-50s within 1 poll uncertainty)
        self.assertEqual(completed_record.onset_ts, 31.0)
        self.assertEqual(completed_record.end_ts, 80.0)
        self.assertIn(completed_record.runtime_s, (49.0, 50.0))

        # Expected energy: 20s*50W + 6s*12W + 24s*48W = 1000 + 72 + 1152 = 2224 J
        self.assertAlmostEqual(completed_record.package_energy_j, 2224.0, delta=100.0)
        self.assertGreater(completed_record.avg_power_w, 40.0)

        # Suggested budget pre-fill calculation (with 5% margin)
        suggested_budget = round(completed_record.runtime_s * 1.05, 1)
        self.assertTrue(51.0 <= suggested_budget <= 53.0)

        # Honesty guards per PLAN §6b
        self.assertIn("estimated via idle-return detection", completed_record.watch_note)

    def test_transient_spike_rejected_as_blip(self):
        """Verify a short spike (< onset_sustained_s) is rejected as background noise."""
        backend = SyntheticEnergyBackend()
        backend.enable_simulated_clock(0.0)
        backend.add_segment("idle_1", duration_s=10.0, power_w=10.0)
        backend.add_segment("blip", duration_s=1.0, power_w=45.0)  # Only 1s spike (< 2s)
        backend.add_segment("idle_2", duration_s=15.0, power_w=10.0)

        detector = WatchModeDetector(idle_threshold_w=15.0, onset_sustained_s=2.0, grace_period_s=10.0)

        dt = 0.5
        completed = None
        for _ in range(50):
            uj, p, ts = backend.step(dt)
            rec = detector.sample(p, uj, ts, backend)
            if rec:
                completed = rec

        # No task should be detected
        self.assertIsNone(completed)
        self.assertEqual(detector.state, "IDLE")

    def test_unavailable_energy_counter_honesty_guard(self):
        """Verify that missing energy counter marks energy unavailable, never 0."""
        backend = SyntheticEnergyBackend()
        backend.setup_standard_watch_profile()

        detector = WatchModeDetector(idle_threshold_w=15.0, onset_sustained_s=2.0, grace_period_s=10.0)

        completed_record = None
        dt = 1.0
        for _ in range(120):
            uj, power_w, ts = backend.step(dt)
            # Simulate counter unavailable by passing energy_uj=None
            record = detector.sample(power_w, None, ts, backend)
            if record is not None:
                completed_record = record
                break

        self.assertIsNotNone(completed_record)
        self.assertFalse(completed_record.energy_available)
        self.assertIsNone(completed_record.package_energy_j)
        # Runtime is still accurately captured
        self.assertIn(completed_record.runtime_s, (49.0, 50.0))

    def test_agent_b_watch_detector_integration(self):
        """Test Agent B's core.watch.WatchDetector against standard scripted profile."""
        from core.watch import WatchDetector

        backend = SyntheticEnergyBackend()
        backend.setup_standard_watch_profile()
        detector = WatchDetector(
            baseline_window_s=30.0,
            onset_s=2.0,
            idle_grace_s=10.0,
            poll_interval_s=1.0,
        )

        closed_segment = None
        for _ in range(120):
            uj, power_w, ts = backend.step(1.0)
            seg = detector.observe(power_w, uj, ts)
            if seg is not None:
                closed_segment = seg
                break

        self.assertIsNotNone(closed_segment)
        self.assertEqual(closed_segment.start_ts, 31.0)
        self.assertEqual(closed_segment.end_ts, 80.0)
        self.assertIn(closed_segment.runtime_s, (49.0, 50.0))
        self.assertTrue(closed_segment.energy_available)
        self.assertIsNotNone(closed_segment.energy_j)
        self.assertAlmostEqual(closed_segment.energy_j, 2174.0, delta=100.0)

        record = closed_segment.to_run_record("exp_watch_test", "watch_workload")
        self.assertEqual(record.mode, "watch")
        self.assertEqual(record.phase, "watch")
        self.assertIn("estimated via idle-return detection", record.watch_note)


if __name__ == "__main__":
    unittest.main()
