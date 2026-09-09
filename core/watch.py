"""Featherweight passive idle/activity detector for watch mode."""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Optional

from core.models import Configuration, RunRecord


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
    ) -> None:
        self.baseline_window_s = baseline_window_s
        self.onset_s = onset_s
        self.idle_grace_s = idle_grace_s
        self.poll_interval_s = poll_interval_s
        self.energy_range_uj = energy_range_uj
        self._baseline_started: Optional[float] = None
        self._baseline_values: list[float] = []
        self.baseline_w: Optional[float] = None
        self.spread_w: float = 0.0
        self.state = "calibrating"
        self._candidate_start: Optional[float] = None
        self._candidate_energy: Optional[int] = None
        self._last_above_ts: Optional[float] = None
        self._last_above_energy: Optional[int] = None
        self._idle_since: Optional[float] = None
        self._segments: list[WatchSegment] = []

    @property
    def segments(self) -> list[WatchSegment]:
        return list(self._segments)

    def observe(self, power_w: float, energy_uj: Optional[int], timestamp: float) -> Optional[WatchSegment]:
        """Consume one low-rate sample; return a segment only when it closes."""
        if self._baseline_started is None:
            self._baseline_started = timestamp
        if self.state == "calibrating":
            self._baseline_values.append(power_w)
            if timestamp - self._baseline_started < self.baseline_window_s:
                return None
            # Process this sample after learning the baseline; it may be the
            # first above-band sample and must not be lost at the boundary.
            self._set_baseline()

        assert self.baseline_w is not None
        in_idle_band = abs(power_w - self.baseline_w) <= max(3.0 * self.spread_w, 2.0)
        if self.state == "idle":
            if in_idle_band:
                self._candidate_start = None
                self._candidate_energy = None
                return None
            if self._candidate_start is None:
                self._candidate_start = timestamp
                self._candidate_energy = energy_uj
            if timestamp - self._candidate_start >= self.onset_s:
                self.state = "active"
                self._last_above_ts = timestamp
                self._last_above_energy = energy_uj
            return None

        # Active: a short in-band dip is absorbed until the grace period elapses.
        if in_idle_band:
            if self._idle_since is None:
                self._idle_since = timestamp
            if timestamp - self._idle_since >= self.idle_grace_s:
                segment = self._close_segment()
                self._segments.append(segment)
                return segment
        else:
            self._idle_since = None
            self._last_above_ts = timestamp
            self._last_above_energy = energy_uj
        return None

    def _set_baseline(self) -> None:
        self.baseline_w = median(self._baseline_values)
        deviations = [abs(value - self.baseline_w) for value in self._baseline_values]
        self.spread_w = median(deviations) if deviations else 0.0
        self.state = "idle"

    def _close_segment(self) -> WatchSegment:
        start = self._candidate_start
        assert start is not None and self._last_above_ts is not None
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
        self._last_above_ts = None
        self._last_above_energy = None
        self._idle_since = None
        return segment
