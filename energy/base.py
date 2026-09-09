"""Energy backend contract (Agent A owns).

Counter semantics (machine-agnostic — machine quirks live in capability reports):

- `read_uj()` returns the raw counter value in microjoules, or None if the read
  fails / is unavailable. Missing energy is NEVER zero.
- `max_range_uj()` returns the advertised wrap range R of the counter.
- Wrap math is the caller's (EnergyAccumulator): delta = (e2 - e1) mod R.
- Backends do no unit conversion beyond uj -> J float (1e6).
- Counter reset detection: a negative-modulo result larger than a plausible
  power ceiling implies a reset or multi-wrap; surface as an error, never guess.
"""

from __future__ import annotations

import time
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class EnergyBackend(Protocol):
    """A hardware-reported package-energy counter."""

    name: str

    def read_uj(self) -> Optional[int]:
        """Raw counter value in microjoules, or None when unavailable."""

    def max_range_uj(self) -> Optional[int]:
        """Advertised counter wrap range in microjoules, if known."""


class EnergyReading(NamedTupleMeta := object):
    pass


from dataclasses import dataclass


@dataclass(frozen=True)
class Reading:
    """One timestamped counter sample."""

    t_monotonic: float
    uj: int


class EnergyAccumulator:
    """Wrap-safe accumulation between two counter samples.

    delta = (e2 - e1) mod R, sampled so at most one wrap occurs between reads.
    A delta larger than `plausible_max_watts * elapsed` implies reset/multi-wrap
    and is reported as an error (never silently guessed).
    """

    def __init__(self, backend: EnergyBackend, plausible_max_watts: float = 200.0):
        self.backend = backend
        self.plausible_max_watts = plausible_max_watts

    def begin(self) -> Reading:
        uj = self.backend.read_uj()
        if uj is None:
            raise EnergyUnavailableError(f"backend {self.backend.name} unavailable at begin")
        return Reading(time.monotonic(), uj)

    def end(self, begin: Reading) -> "EnergyDelta":
        uj = self.backend.read_uj()
        if uj is None:
            raise EnergyUnavailableError(f"backend {self.backend.name} unavailable at end")
        return self.delta(begin, Reading(time.monotonic(), uj))

    def delta(self, r1: Reading, r2: Reading) -> "EnergyDelta":
        R = self.backend.max_range_uj()
        if R and R > 0:
            d = (r2.uj - r1.uj) % R
        else:
            d = r2.uj - r1.uj
            if d < 0:
                raise EnergyResetError("counter went backwards with no known range")
        elapsed = r2.t_monotonic - r1.t_monotonic
        plausible_uj = self.plausible_max_watts * max(elapsed, 1e-9) * 1e6
        if d > plausible_uj:
            raise EnergyResetError(
                f"delta {d} uJ exceeds plausible {int(plausible_uj)} uJ over {elapsed:.3f}s — reset or multi-wrap"
            )
        return EnergyDelta(uj=d, joules=d / 1e6, elapsed_s=elapsed)


@dataclass(frozen=True)
class EnergyDelta:
    uj: int
    joules: float
    elapsed_s: float


class EnergyError(Exception):
    pass


class EnergyUnavailableError(EnergyError):
    pass


class EnergyResetError(EnergyError):
    pass


class PowercapBackend:
    """sysfs powercap energy counter (verified backend on the demo laptop).

    Path is discovered, not hardcoded — see core/discovery.py.
    """

    def __init__(self, path: str, max_range_uj: Optional[int] = None):
        self.name = f"powercap:{path.rsplit('/', 1)[-1]}"
        self.path = path
        self._range = max_range_uj

    def read_uj(self) -> Optional[int]:
        try:
            with open(self.path) as f:
                return int(f.read().strip())
        except OSError:
            return None

    def max_range_uj(self) -> Optional[int]:
        if self._range is not None:
            return self._range
        try:
            base = self.path.rsplit("/", 1)[0]
            with open(f"{base}/max_energy_range_uj") as f:
                return int(f.read().strip())
        except OSError:
            return None


class HelperEnergyBackend:
    """sysfs powercap counter read via the joulectrl helper daemon.

    Used on systems where powercap sysfs is root-only (-r--------)
    so unprivileged processes (like the dashboard API) can read the real
    hardware energy counter without needing root permissions themselves.
    """

    def __init__(self, helper: Any = None, max_range_uj: Optional[int] = 65_532_610_987):
        self.name = "helper:read_energy"
        self._helper = helper
        self._range = max_range_uj

    def read_uj(self) -> Optional[int]:
        try:
            if self._helper is None:
                from helper.client import HelperClient
                self._helper = HelperClient()
            resp = self._helper.read_energy()
            if resp.get("ok") and "uj" in resp:
                return int(resp["uj"])
            return None
        except Exception:
            return None

    def max_range_uj(self) -> Optional[int]:
        return self._range

