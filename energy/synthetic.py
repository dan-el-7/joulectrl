"""energy/synthetic.py — Synthetic energy backend for testing and simulation (Agent B owned).

Implements wrapping, resets, unavailability, and scripted power profiles (§6b).
Designed to conform to the EnergyBackend semantics Agent A publishes in energy/base.py.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

# Default hardware counter range from demo laptop RAPL (approx 65.5 kJ)
DEFAULT_MAX_ENERGY_RANGE_UJ: int = 65_532_610_987


@dataclass
class PowerProfileSegment:
    """A segment in a scripted power profile for watch-mode testing (§6b)."""
    name: str
    duration_s: float
    power_w: float
    spread_w: float = 0.0


class SyntheticEnergyBackend:
    """Synthetic counter implementing hardware RAPL counter semantics.
    
    Features:
    - Wraps at max_energy_range_uj per PLAN §5 modulo arithmetic.
    - Can simulate unavailable reads (returning None, never 0).
    - Can simulate counter resets (e.g. platform reset / suspend).
    - Includes a scripted power profile generator for watch mode tests (AGENTS.md §6b).
    """

    def __init__(
        self,
        initial_uj: int = 1_000_000,
        max_energy_range_uj: int = DEFAULT_MAX_ENERGY_RANGE_UJ,
        scope: str = "package-0",
        unit: str = "uj",
    ) -> None:
        self.name: str = "synthetic"
        self.scope = scope
        self.unit = unit
        self.max_energy_range_uj = max_energy_range_uj
        self._current_uj: int = initial_uj % max_energy_range_uj
        self._available: bool = True
        self._simulated_time_s: float = 0.0
        self._use_simulated_clock: bool = False
        self._reset_flag: bool = False

        # Scripted power profile player (§6b)
        self._profile_segments: list[PowerProfileSegment] = []
        self._current_segment_idx: int = 0
        self._segment_elapsed_s: float = 0.0

    # -----------------------------------------------------------------------
    # Core EnergyBackend Protocol (Agent A's energy/base.py)
    # -----------------------------------------------------------------------

    def read_uj(self) -> Optional[int]:
        """Raw counter value in microjoules, or None when unavailable."""
        if not self._available:
            return None
        return self._current_uj

    def max_range_uj(self) -> Optional[int]:
        """Advertised counter wrap range in microjoules."""
        return self.max_energy_range_uj

    def read_energy_uj(self) -> Optional[int]:
        """Alias for read_uj() for backwards/explicit naming compatibility."""
        return self.read_uj()

    def read(self) -> tuple[Optional[int], float]:
        """Read current energy counter and monotonic timestamp.
        
        Returns:
            (energy_uj or None, monotonic_timestamp_seconds)
        """
        ts = self._simulated_time_s if self._use_simulated_clock else time.monotonic()
        uj = self.read_energy_uj()
        return uj, ts

    def compute_delta_uj(self, start_uj: Optional[int], end_uj: Optional[int]) -> Optional[int]:
        """Compute wrap-safe energy delta between two counter samples in microjoules.
        
        Using modulo arithmetic from PLAN Section 5:
            delta = (end_uj - start_uj) % max_energy_range_uj
            
        Returns:
            Delta in microjoules, or None if either sample was unavailable or
            if an unhandled reset occurred.
        """
        if start_uj is None or end_uj is None:
            return None
        
        if not (0 <= start_uj < self.max_energy_range_uj and 0 <= end_uj < self.max_energy_range_uj):
            # Out of valid counter range
            return None

        # Modulo wrap arithmetic
        delta = (end_uj - start_uj) % self.max_energy_range_uj
        return delta

    def compute_delta_j(self, start_uj: Optional[int], end_uj: Optional[int]) -> Optional[float]:
        """Compute wrap-safe energy delta between two counter samples in Joules."""
        delta_uj = self.compute_delta_uj(start_uj, end_uj)
        if delta_uj is None:
            return None
        return delta_uj / 1_000_000.0

    # -----------------------------------------------------------------------
    # Fault Injection & Testing Controls
    # -----------------------------------------------------------------------

    def set_available(self, available: bool) -> None:
        """Toggle counter availability for failure-testing."""
        self._available = available

    def is_available(self) -> bool:
        return self._available

    def advance_uj(self, delta_uj: int, dt_s: float = 0.0) -> None:
        """Advance the counter by delta_uj, wrapping at max_energy_range_uj."""
        # Time is independent of counter availability: watch-mode detection must
        # retain monotonic timing while energy reads are temporarily unavailable.
        if dt_s > 0:
            self._simulated_time_s += dt_s
        if not self._available:
            return
        self._current_uj = (self._current_uj + delta_uj) % self.max_energy_range_uj

    def advance_j(self, joules: float, dt_s: float = 0.0) -> None:
        """Advance the counter by Joules."""
        delta_uj = int(joules * 1_000_000.0)
        self.advance_uj(delta_uj, dt_s=dt_s)

    def trigger_wrap(self, margin_uj: int = 100_000, step_uj: int = 500_000) -> tuple[int, int]:
        """Convenience method to set counter just before max_range and wrap past it.
        
        Returns:
            (start_uj, end_uj) crossing the wrap boundary.
        """
        start_uj = self.max_energy_range_uj - margin_uj
        self._current_uj = start_uj
        self.advance_uj(step_uj)
        end_uj = self._current_uj
        return start_uj, end_uj

    def trigger_reset(self, new_val_uj: int = 0) -> None:
        """Simulate an unadvertised counter reset."""
        self._current_uj = new_val_uj % self.max_energy_range_uj
        self._reset_flag = True

    # -----------------------------------------------------------------------
    # Scripted Power Profiles (§6b watch-mode testing)
    # -----------------------------------------------------------------------

    def enable_simulated_clock(self, start_time_s: float = 0.0) -> None:
        """Use simulated monotonic clock instead of system monotonic clock."""
        self._use_simulated_clock = True
        self._simulated_time_s = start_time_s

    def add_segment(self, name: str, duration_s: float, power_w: float, spread_w: float = 0.0) -> None:
        """Add a segment to the scripted power profile."""
        self._profile_segments.append(
            PowerProfileSegment(name=name, duration_s=duration_s, power_w=power_w, spread_w=spread_w)
        )

    def setup_standard_watch_profile(self) -> None:
        """Load standard watch profile:
        1. idle: 10 W for 30s
        2. onset / task phase 1: 50 W for 20s
        3. mid-task dip: 12 W for 6s (should NOT cause task termination per dip rule)
        4. task phase 2: 48 W for 24s
        5. return to idle: 10 W for 40s
        """
        self._profile_segments = [
            PowerProfileSegment("initial_idle", duration_s=30.0, power_w=10.0, spread_w=0.5),
            PowerProfileSegment("task_active_1", duration_s=20.0, power_w=50.0, spread_w=2.0),
            PowerProfileSegment("task_mid_dip", duration_s=6.0, power_w=12.0, spread_w=0.5),
            PowerProfileSegment("task_active_2", duration_s=24.0, power_w=48.0, spread_w=2.0),
            PowerProfileSegment("return_idle", duration_s=40.0, power_w=10.0, spread_w=0.5),
        ]
        self._current_segment_idx = 0
        self._segment_elapsed_s = 0.0
        self.enable_simulated_clock(0.0)

    def current_power_w(self) -> float:
        """Return the current instantaneous power in Watts based on active segment."""
        if not self._profile_segments or self._current_segment_idx >= len(self._profile_segments):
            return 10.0  # Default idle baseline
        return self._profile_segments[self._current_segment_idx].power_w

    def step(self, dt_s: float) -> tuple[Optional[int], float, float]:
        """Advance time by dt_s in the scripted profile and advance energy accordingly.
        
        Returns:
            (energy_uj, current_power_w, current_simulated_time_s)
        """
        power_w = self.current_power_w()
        energy_j = power_w * dt_s
        self.advance_j(energy_j, dt_s=dt_s)

        if self._profile_segments and self._current_segment_idx < len(self._profile_segments):
            self._segment_elapsed_s += dt_s
            seg = self._profile_segments[self._current_segment_idx]
            if self._segment_elapsed_s >= seg.duration_s:
                self._current_segment_idx += 1
                self._segment_elapsed_s = 0.0

        uj, ts = self.read()
        return uj, power_w, ts
