"""api/live.py — live wiring for Agent C's API (SSE + watch mode).

Bridges Agent B's core primitives to the API layer without owning their logic:

- ``subscribe_experiment_events`` — bridge B's synchronous EventBus subscribers
  to async SSE (replay(0) initial burst, then live follow; the run always wins
  over the dashboard — see core/events.py).
- ``WatchService`` — B's WatchDetector (core/watch.py) fed by the best available
  energy source: A's real PowercapBackend on the demo laptop (via discovery),
  B's SyntheticEnergyBackend scripted profile on dev machines. Watch is
  read-only: no controls, no helper lease, missing energy is never zero (§6b).
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from core.events import Event, ExperimentEvents, default_bus
from core.watch import WatchDetector, WatchSegment

# ---------------------------------------------------------------------------
# SSE bridge: B's sync EventBus -> async generator
# ---------------------------------------------------------------------------


class EventBuffer:
    """Thread-safe buffer of pending Events with an asyncio wake-up."""

    def __init__(self) -> None:
        import threading

        self._lock = threading.Lock()
        self._events: list[Event] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._event: Optional[asyncio.Event] = None

    def attach(self, loop: asyncio.AbstractEventLoop) -> None:
        with self._lock:
            self._loop = loop
            self._event = asyncio.Event()

    def push(self, event: Event) -> None:
        with self._lock:
            self._events.append(event)
            loop = self._loop
            ev = self._event
        if loop is not None and ev is not None:
            try:
                loop.call_soon_threadsafe(ev.set)
            except RuntimeError:
                pass  # loop closed

    def pop_all(self) -> list[Event]:
        with self._lock:
            events = self._events
            self._events = []
            if self._event is not None:
                self._event.clear()
            return events

    async def wait(self, timeout_s: float) -> bool:
        ev = self._event
        if ev is None:
            await asyncio.sleep(timeout_s)
            return False
        try:
            await asyncio.wait_for(ev.wait(), timeout=timeout_s)
            return True
        except asyncio.TimeoutError:
            return False


async def stream_experiment_events(
    experiment_id: str,
    keepalive_s: float = 15.0,
    max_idle_s: float = 3600.0,
    on_event: Optional[Callable[[Event], Awaitable[None]]] = None,
) -> Any:
    """Yield SSE frames: replay(0) burst, then live events from B's bus.

    Never raises on subscriber errors — B's bus already swallows those; this
    generator additionally guarantees the SSE stream outlives any single event.
    """
    evlog: ExperimentEvents = default_bus().for_experiment(experiment_id)
    buffer = EventBuffer()
    buffer.attach(asyncio.get_running_loop())

    # Replay burst from history…
    last_seq = 0
    for event in evlog.replay(0):
        yield event.sse_frame()
        last_seq = max(last_seq, event.seq)
    if on_event is not None:
        for event in evlog.replay(0):
            await on_event(event)

    # …then subscribe, and close the replay→subscribe race: anything published
    # in between is in history but missed by the buffer — re-read and emit.
    unsubscribe = evlog.subscribe(buffer.push)
    for event in evlog.replay(last_seq):
        yield event.sse_frame()
        last_seq = max(last_seq, event.seq)
        if on_event is not None:
            await on_event(event)

    try:
        idle = 0.0
        while idle < max_idle_s:
            has_events = await buffer.wait(timeout_s=keepalive_s / 2)
            events = buffer.pop_all()
            if events:
                idle = 0.0
                for event in events:
                    yield event.sse_frame()
                    if on_event is not None:
                        await on_event(event)
            elif not has_events:
                idle += keepalive_s / 2
                yield ": keepalive\n\n"
    finally:
        unsubscribe()


# ---------------------------------------------------------------------------
# Watch service: B's detector + best-available energy source
# ---------------------------------------------------------------------------


def _best_energy_backend() -> tuple[Any, dict[str, Any]]:
    """Return (backend, source_info) — real powercap if readable, else synthetic.

    Real path: A's discovery + PowercapBackend (energy/base.py). On machines
    where the counter is root-only (returns None), fall back to the synthetic
    scripted profile so the dashboard flow is demonstrable everywhere — the
    source is always labeled, never silent (honesty guards, §6b).
    """
    try:
        from core.discovery import find_package_energy_paths
        from energy.base import PowercapBackend

        for domain in find_package_energy_paths():
            backend = PowercapBackend(
                domain["path"], max_range_uj=domain.get("max_energy_range_uj")
            )
            probe = backend.read_uj()
            if probe is not None:
                info = {
                    "source": "powercap",
                    "domain": domain.get("domain", "package-0"),
                    "path": domain["path"],
                    "synthetic": False,
                }
                return backend, info
    except Exception:
        pass  # discovery is Linux-only; dev machines fall through to synthetic

    # Helper daemon probe: on machines where powercap is root-only (-r--------, e.g. demo laptop),
    # the helper daemon provides unprivileged read_energy() access to the real hardware counter.
    try:
        from energy.base import HelperEnergyBackend
        from helper.client import HelperClient

        h = HelperClient()
        probe = h.read_energy()
        if probe.get("ok") and probe.get("uj") is not None:
            backend = HelperEnergyBackend(h)
            info = {
                "source": "helper_powercap",
                "domain": "package-0",
                "path": "/sys/class/powercap/intel-rapl:0/energy_uj",
                "synthetic": False,
                "note": "Live hardware RAPL counter via joulectrl helper daemon",
            }
            return backend, info
    except Exception:
        pass

    from energy.synthetic import SyntheticEnergyBackend

    backend = SyntheticEnergyBackend()
    backend.setup_standard_watch_profile()
    info = {
        "source": "synthetic_scripted",
        "domain": "package-0",
        "path": None,
        "synthetic": True,
        "note": "synthetic scripted power profile (dev machine; no readable package counter)",
    }
    return backend, info


class WatchService:
    """Passive watch session on B's WatchDetector (read-only, §6b).

    Polls the backend at 0.5–1 Hz, feeds the detector, and exposes SSE frames
    for samples / state / segments. On the dev machine the synthetic backend
    runs a scripted profile at accelerated time so a full idle→activity→idle
    cycle (with mid-task dip) demonstrably closes a segment in ~2 s wall time.
    """

    # Dev-machine acceleration: one wall second advances simulated time by
    # this factor, so the scripted 120 s profile plays out in ~4 s.
    DEV_TIME_SCALE = 30.0

    def __init__(
        self,
        *,
        poll_hz: float = 1.0,
        onset_s: float = 3.0,
        idle_grace_s: float = 10.0,
        baseline_window_s: float = 30.0,
        backend: Optional[Any] = None,
        time_scale: Optional[float] = None,
    ) -> None:
        self.backend, self.source_info = (
            (backend, {"source": "injected", "synthetic": bool(getattr(backend, "_profile_segments", None))})
            if backend is not None
            else _best_energy_backend()
        )
        self.detector = WatchDetector(
            baseline_window_s=baseline_window_s,
            onset_s=onset_s,
            idle_grace_s=idle_grace_s,
            poll_interval_s=1.0 / poll_hz,
        )
        synthetic = self.source_info.get("synthetic", False)
        self._time_scale = time_scale if time_scale is not None else (
            WatchService.DEV_TIME_SCALE if synthetic else 1.0
        )
        self._sim_ts: Optional[float] = None
        # Wall-clock anchor for labeling timestamps: synthetic profiles run on
        # a simulated clock, so labels = start_wall + (ts - start_sim).
        self._start_wall = time.time()
        self._start_sim: Optional[float] = None if not synthetic else 0.0
        self._seg_counter = 0
        self.last_power_w: Optional[float] = None
        self.started_at = time.time()

    # -- polling ----------------------------------------------------------

    def _poll_interval_wall(self) -> float:
        return (1.0 / max(self.detector.poll_interval_s, 0.5)) / self._time_scale

    def _profile_exhausted(self) -> bool:
        """True when a synthetic scripted profile has fully played out."""
        return bool(getattr(self.backend, "_profile_segments", None)) and (
            getattr(self.backend, "_current_segment_idx", 0)
            >= len(getattr(self.backend, "_profile_segments", []))
        )

    def _sample_once(self) -> Optional[dict[str, Any]]:
        """Take one sample (real or scripted), feed the detector, return frame data."""
        synthetic = self.source_info.get("synthetic", False)
        if synthetic:
            # Scripted profile: step simulated time and read power + energy.
            dt_sim = self.detector.poll_interval_s
            energy_uj, power_w, sim_t = self.backend.step(dt_sim)
            ts = sim_t
        else:
            read = self.backend.read_uj()
            energy_uj = read
            power_w = self._power_from_energy(energy_uj)
            ts = time.monotonic()

        self.last_power_w = power_w
        segment = self.detector.observe(power_w, energy_uj, ts)
        frame = {
            "timestamp": _iso_now(),
            "power_w": round(power_w, 2) if power_w is not None else None,
            "in_idle_band": self._in_idle_band(power_w),
        }
        if segment is not None:
            frame["closed_segment"] = segment
        return frame

    def _power_from_energy(self, energy_uj: Optional[int]) -> Optional[float]:
        """Derive instantaneous watts from consecutive counter reads."""
        if energy_uj is None:
            return None
        if self._sim_ts is None:
            self._sim_ts = time.monotonic()
            self._prev_energy_uj = energy_uj
            self._prev_energy_ts = self._sim_ts
            return None
        now = time.monotonic()
        dt = now - self._prev_energy_ts
        if dt <= 0:
            return None
        rng = self.backend.max_range_uj() if callable(getattr(self.backend, "max_range_uj", None)) else None
        delta = self._delta_uj(self._prev_energy_uj, energy_uj, rng)
        self._prev_energy_uj = energy_uj
        self._prev_energy_ts = now
        return delta / 1e6 / dt if delta is not None else None

    @staticmethod
    def _delta_uj(prev: int, cur: int, rng: Optional[int]) -> Optional[int]:
        if rng and rng > 0:
            return (cur - prev) % rng
        d = cur - prev
        return d if d >= 0 else None

    def _in_idle_band(self, power_w: Optional[float]) -> bool:
        if power_w is None or self.detector.baseline_w is None:
            return False
        return abs(power_w - self.detector.baseline_w) <= max(
            3.0 * self.detector.spread_w, 2.0
        )

    # -- SSE frames -------------------------------------------------------

    def sample_frame(self, sample: dict[str, Any]) -> str:
        import json

        payload = {k: v for k, v in sample.items() if k != "closed_segment"}
        return f"event: watch_sample\ndata: {json.dumps(payload)}\n\n"

    def state_frame(self) -> str:
        import json

        payload = {
            "state": self.detector.state,
            "baseline_median_w": self.detector.baseline_w,
            "baseline_spread_w": self.detector.spread_w,
        }
        return f"event: watch_state\ndata: {json.dumps(payload)}\n\n"

    def segment_frame(self, segment: WatchSegment) -> dict[str, Any]:
        """API-shaped watch segment record (§6b honesty guards included)."""
        self._seg_counter += 1
        energy_j = segment.energy_j
        runtime_s = segment.runtime_s
        # Suggested budget via Agent B's deterministic suggest_budget (runtime * 1.05 floor)
        from core.budget import suggest_budget
        suggested = suggest_budget([segment]) or round(runtime_s * 1.05, 2)
        onset_label = self._label_ts(segment.start_ts)
        end_label = self._label_ts(segment.end_ts)
        return {
            "segment_id": f"seg_{self._seg_counter:02d}",
            "onset_ts": onset_label,
            "end_ts": end_label,
            # REST alias per docs/API.md §3.9 (stop response shape)
            "onset_timestamp": onset_label,
            "end_timestamp": end_label,
            "duration_s": round(runtime_s, 2),
            "estimated_energy_j": round(energy_j, 1) if energy_j is not None else None,
            "energy_available": energy_j is not None,
            "suggested_budget_s": suggested,
            "mode": "watch",
            "note": "Estimated via idle-return detection (first spike to last spike, idle tail trimmed). Uncertainty ±"
            f"{self.detector.poll_interval_s:.1f}s.",
        }

    def _label_ts(self, ts: float) -> Optional[str]:
        """Honest wall-clock label: real monotonic anchored to now; simulated
        seconds anchored to the session's start wall time."""
        if self._start_sim is not None:
            wall = self._start_wall + (ts - self._start_sim)
        else:
            try:
                wall = time.time() - (time.monotonic() - ts)
            except (OverflowError, ValueError):
                return _iso_now()
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(wall))

    def status_dict(self) -> dict[str, Any]:
        active = self.detector.state not in {"stopped"}
        return {
            "active": active,
            "state": self.detector.state,
            "source": self.source_info,
            "poll_hz": round(1.0 / self.detector.poll_interval_s, 2),
            "current_power_w": round(self.last_power_w, 2) if self.last_power_w is not None else None,
            "baseline_median_w": self.detector.baseline_w,
            "baseline_spread_w": self.detector.spread_w,
            "active_segment_elapsed_s": None,
            "completed_segments_count": len(self.detector.segments),
        }


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
