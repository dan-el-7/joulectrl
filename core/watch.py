"""Featherweight passive idle/activity detector for watch mode."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from statistics import median
from typing import Callable, Optional

from core.models import Configuration, RunRecord

# Same plausibility ceiling as energy.base.EnergyAccumulator: a segment delta
# implying more than this sustained over the segment means counter reset/multi-wrap.
PLAUSIBLE_MAX_W = 200.0


@dataclass
class WatchSegment:
    start_ts: float
    end_ts: float
    start_energy_uj: Optional[int]
    end_energy_uj: Optional[int]
    energy_range_uj: Optional[int]
    baseline_w: float
    spread_w: float
    poll_interval_s: float
    energy_available: bool = True

    @property
    def runtime_s(self) -> float:
        return max(0.0, self.end_ts - self.start_ts)

    @property
    def energy_j(self) -> Optional[float]:
        if not self.energy_available or self.start_energy_uj is None or self.end_energy_uj is None:
            return None
        if self.energy_range_uj and self.energy_range_uj > 0:
            delta = (self.end_energy_uj - self.start_energy_uj) % self.energy_range_uj
        else:
            delta = self.end_energy_uj - self.start_energy_uj
            if delta < 0:
                return None
        # Counter reset / multi-wrap guard: never report an implausible delta as Joules.
        if delta > PLAUSIBLE_MAX_W * max(self.runtime_s, 1e-9) * 1e6:
            return None
        return delta / 1_000_000.0

    def to_run_record(self, experiment_id: str, workload_name: str, config: Optional[Configuration] = None) -> RunRecord:
        return RunRecord(
            run_id=f"watch-{self.start_ts:.6f}",
            experiment_id=experiment_id,
            config_id=config.id if config else "watch",
            workload_name=workload_name,
            repetition=1,
            mode="watch",
            phase="watch",
            start_time_monotonic=self.start_ts,
            end_time_monotonic=self.end_ts,
            runtime_s=self.runtime_s,
            package_energy_j=self.energy_j,
            start_energy_uj=self.start_energy_uj,
            end_energy_uj=self.end_energy_uj,
            energy_available=self.energy_available and self.energy_j is not None,
            status="success",
            output_verified=True,
            configuration=config,
            idle_baseline_w=self.baseline_w,
            idle_spread_w=self.spread_w,
            onset_ts=self.start_ts,
            end_ts=self.end_ts,
            poll_interval_s=self.poll_interval_s,
            detection_uncertainty_s=self.poll_interval_s,
            watch_note="estimated via idle-return detection",
        )


class WatchDetector:
    """Detect one or more task windows without applying controls."""

    def __init__(
        self,
        *,
        baseline_window_s: float = 30.0,
        onset_s: float = 3.0,
        idle_grace_s: float = 10.0,
        poll_interval_s: float = 1.0,
        energy_range_uj: Optional[int] = None,
        initial_baseline_w: Optional[float] = None,
        on_active: Optional[Callable[[float, float], None]] = None,
        on_idle: Optional[Callable[[WatchSegment], None]] = None,
    ) -> None:
        self.baseline_window_s = baseline_window_s
        self.onset_s = onset_s
        self.idle_grace_s = idle_grace_s
        self.poll_interval_s = poll_interval_s
        self.energy_range_uj = energy_range_uj
        self.on_active = on_active
        self.on_idle = on_idle
        self._baseline_started: Optional[float] = None
        self._baseline_values: list[float] = []

        if initial_baseline_w is not None and initial_baseline_w > 0:
            self.baseline_w = float(initial_baseline_w)
            self.spread_w = 1.0
            self.state = "idle"
        else:
            self.baseline_w = None
            self.spread_w = 0.0
            self.state = "calibrating"

        self._candidate_start: Optional[float] = None
        self._candidate_energy: Optional[int] = None
        self._candidate_active_samples: int = 0
        self._last_above_ts: Optional[float] = None
        self._last_above_energy: Optional[int] = None
        self._idle_since: Optional[float] = None
        self._segments: list[WatchSegment] = []

    @property
    def segments(self) -> list[WatchSegment]:
        return list(self._segments)

    @property
    def threshold_w(self) -> Optional[float]:
        """Dynamic spike threshold based on observed rough idle baseline.
        
        A sudden compute spike must clearly stand out from the ambient idle:
        1. At least 3 * spread_w (noise envelope rejection)
        2. At least 35% above the rough idle baseline (relative power step)
        3. Minimum 3.5 W absolute floor (prevents false positives on low-power idles)
        """
        if self.baseline_w is None:
            return None
        delta = max(3.0 * self.spread_w, 0.35 * self.baseline_w, 3.5)
        return self.baseline_w + delta

    @property
    def idle_band_max_w(self) -> Optional[float]:
        """Dynamic power ceiling for declaring return to idle."""
        if self.baseline_w is None:
            return None
        delta = max(2.0 * self.spread_w, 0.20 * self.baseline_w, 2.5)
        return self.baseline_w + delta

    def observe(self, power_w: float, energy_uj: Optional[int], timestamp: float) -> Optional[WatchSegment]:
        """Consume one low-rate sample; return a segment only when it closes."""
        if self._baseline_started is None:
            self._baseline_started = timestamp
        if self.state == "calibrating":
            self._baseline_values.append(power_w)
            min_samples = 2
            if len(self._baseline_values) >= min_samples:
                # If a sudden spike arrives during the first few samples,
                # immediately treat the prior samples as rough idle!
                prior_median = statistics.median(self._baseline_values[:-1])
                if power_w > prior_median + max(0.35 * prior_median, 3.5):
                    self.baseline_w = float(prior_median)
                    self.spread_w = 0.5
                    self.state = "idle"
                elif timestamp - self._baseline_started >= min(self.baseline_window_s, 2.0):
                    self._set_baseline()

            if self.state == "calibrating":
                return None

        assert self.baseline_w is not None
        thresh = self.threshold_w
        is_above_band = thresh is not None and power_w > thresh
        idle_ceil = self.idle_band_max_w
        in_idle_band = idle_ceil is not None and power_w <= idle_ceil

        if self.state == "idle":
            if is_above_band:
                if self._candidate_start is None:
                    # Capture exact first moment power spiked above idle baseline
                    self._candidate_start = timestamp
                    self._candidate_energy = energy_uj
                    self._candidate_active_samples = 1
                else:
                    self._candidate_active_samples += 1

                # Confirm active once sustained beyond onset duration
                if (timestamp - self._candidate_start >= self.onset_s) or (self._candidate_active_samples >= int(self.onset_s)):
                    self.state = "active"
                    self._last_above_ts = timestamp
                    self._last_above_energy = energy_uj
                    self._idle_since = None
                    if self.on_active is not None:
                        try:
                            self.on_active(timestamp, power_w)
                        except Exception:
                            pass
                return None
            else:
                # Brief dip during onset: do not discard candidate start immediately
                # unless idle persists longer than onset window (rejects blips)
                if self._candidate_start is not None:
                    if timestamp - self._candidate_start > max(self.onset_s + 2.0, 4.0):
                        self._candidate_start = None
                        self._candidate_energy = None
                        self._candidate_active_samples = 0
                else:
                    # No pending spike: slowly re-learn idle baseline so ambient
                    # drift (browser video, background load) is tracked, not fought.
                    self._adapt_baseline(power_w)
                return None

        # Active: a short in-band dip is absorbed until the grace period elapses (Geekbench bursty phases).
        if in_idle_band:
            if self._idle_since is None:
                self._idle_since = timestamp
            if timestamp - self._idle_since >= self.idle_grace_s:
                segment = self._close_segment()
                self._segments.append(segment)
                if self.on_idle is not None:
                    try:
                        self.on_idle(segment)
                    except Exception:
                        pass
                return segment
        else:
            # Active spike: update last above-band timestamp & energy; absorb preceding dip
            self._idle_since = None
            self._last_above_ts = timestamp
            self._last_above_energy = energy_uj
        return None

    def _adapt_baseline(self, power_w: float) -> None:
        """Rolling-window idle re-estimation: absorb ambient drift (e.g. browser
        video raising idle power 8W→18W) while no spike candidate is pending.
        Baseline is frozen during candidates/active segments so a workload's
        ramp-up can never be absorbed into the threshold."""
        self._baseline_values.append(power_w)
        cap = max(8, int(self.baseline_window_s / max(self.poll_interval_s, 0.1)))
        if len(self._baseline_values) > cap:
            self._baseline_values = self._baseline_values[-cap:]
        self._set_baseline()

    def _set_baseline(self) -> None:
        self.baseline_w = median(self._baseline_values)
        deviations = [abs(value - self.baseline_w) for value in self._baseline_values]
        self.spread_w = median(deviations) if deviations else 0.0
        self.state = "idle"

    def _close_segment(self) -> WatchSegment:
        start = self._candidate_start
        assert start is not None and self._last_above_ts is not None
        # Trim trailing idle grace: end_ts is strictly the last above-band sample
        segment = WatchSegment(
            start_ts=start,
            end_ts=self._last_above_ts,
            start_energy_uj=self._candidate_energy,
            end_energy_uj=self._last_above_energy,
            energy_range_uj=self.energy_range_uj,
            baseline_w=self.baseline_w or 0.0,
            spread_w=self.spread_w,
            poll_interval_s=self.poll_interval_s,
            energy_available=self._candidate_energy is not None and self._last_above_energy is not None,
        )
        self.state = "idle"
        self._candidate_start = None
        self._candidate_energy = None
        self._candidate_active_samples = 0
        self._last_above_ts = None
        self._last_above_energy = None
        self._idle_since = None
        return segment

