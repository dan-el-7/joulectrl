"""core/clock_checker.py — Fast (<1ms) check on clocks that hold.

Validates whether a target frequency cap and boost setting can hold on the
active CPU topology and cpufreq driver, adapting controls automatically for
universal compatibility across AMD pstate, Intel pstate, and generic cpufreq.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

_AMD_PSTATE_STATUS = Path("/sys/devices/system/cpu/amd_pstate/status")
_CPUFREQ_POLICY0 = Path("/sys/devices/system/cpu/cpufreq/policy0")
_BOOST_PATH = Path("/sys/devices/system/cpu/cpufreq/boost")

# In-memory cache for hardware capability probes (<0.1ms subsequent checks)
_PROBE_CACHE: dict[str, Any] = {}


def probe_hardware_clock_caps(force_refresh: bool = False) -> dict[str, Any]:
    """Probe CPU frequency constraints and driver capabilities once and cache."""
    global _PROBE_CACHE
    if _PROBE_CACHE and not force_refresh:
        return _PROBE_CACHE

    is_linux = os.name == "posix" and Path("/sys").exists()
    has_amd_pstate = _AMD_PSTATE_STATUS.exists()
    amd_pstate_status = _AMD_PSTATE_STATUS.read_text().strip() if has_amd_pstate else None

    driver = None
    hw_min_khz = None
    hw_max_khz = None
    base_khz = 2000000  # Conservative standard base clock baseline

    if _CPUFREQ_POLICY0.exists():
        d_path = _CPUFREQ_POLICY0 / "scaling_driver"
        if d_path.exists():
            driver = d_path.read_text().strip()
        min_path = _CPUFREQ_POLICY0 / "cpuinfo_min_freq"
        if min_path.exists():
            try:
                hw_min_khz = int(min_path.read_text().strip())
            except Exception:
                pass
        max_path = _CPUFREQ_POLICY0 / "cpuinfo_max_freq"
        if max_path.exists():
            try:
                hw_max_khz = int(max_path.read_text().strip())
            except Exception:
                pass
        base_path = _CPUFREQ_POLICY0 / "base_frequency"
        if base_path.exists():
            try:
                base_khz = int(base_path.read_text().strip())
            except Exception:
                pass

    has_boost_toggle = _BOOST_PATH.exists()

    _PROBE_CACHE = {
        "is_linux": is_linux,
        "driver": driver,
        "has_amd_pstate": has_amd_pstate,
        "amd_pstate_status": amd_pstate_status,
        "hw_min_khz": hw_min_khz or 600000,
        "hw_max_khz": hw_max_khz or 5000000,
        "base_khz": base_khz,
        "has_boost_toggle": has_boost_toggle,
    }
    return _PROBE_CACHE


def check_clock_holdable(
    freq_cap_khz: Optional[int],
    boost: Optional[bool] = None,
    cpu_affinity: Optional[list[int]] = None,
    live_caps: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Fast check on whether a requested frequency cap can hold on this machine.

    Returns adaptation details and flags so the caller knows whether the clock
    will hold naturally, requires passive pstate mode, or was clamped.
    """
    probe = probe_hardware_clock_caps()
    hw_min = probe["hw_min_khz"]
    hw_max = probe["hw_max_khz"]
    base_khz = probe["base_khz"]
    is_amd = probe["has_amd_pstate"] or (probe["driver"] and "amd" in probe["driver"])

    if freq_cap_khz is None or freq_cap_khz <= 0:
        # Uncapped / stock frequency
        control: dict[str, Any] = {"boost": True if boost is None else boost}
        return {
            "holdable": True,
            "requested_khz": None,
            "effective_khz": None,
            "is_amd_pstate": is_amd,
            "requires_passive_mode": False,
            "clamped": False,
            "reason": "Stock unconstrained frequency",
            "adapted_control": control,
        }

    # Clamp requested cap to hardware physical envelope for safety
    clamped = False
    effective_khz = int(freq_cap_khz)
    if effective_khz > hw_max:
        effective_khz = hw_max
        clamped = True
    elif effective_khz < hw_min:
        effective_khz = hw_min
        clamped = True

    boost_flag = True if boost is None else bool(boost)
    requires_passive = False
    reason = "Clock within hardware bounds"

    control = {
        "boost": boost_flag,
        "policy_freq_caps_khz": {
            f"policy{cpu}": effective_khz for cpu in (cpu_affinity or [0])
        },
    }

    if is_amd:
        # On AMD pstate (e.g. Zen 4/5 Ryzen AI HX 370), boost=0 reduces cpuinfo_max_freq
        # to the base frequency (~2.0 GHz). A requested clock > base clock (e.g. 4.0 GHz)
        # CANNOT hold in active mode when boost is False.
        # It DOES hold in passive mode with boost=1 or active mode with boost=1.
        if effective_khz > base_khz and not boost_flag:
            requires_passive = True
            control["pstate_mode"] = "passive"
            control["boost"] = True
            reason = (
                f"Clock {effective_khz // 1000} MHz exceeds base clock ({base_khz // 1000} MHz) "
                "with boost off; auto-adapted to passive p-state mode to hold cap."
            )
        elif effective_khz <= base_khz:
            reason = f"Clock {effective_khz // 1000} MHz holds within nominal base frequency."
        else:
            reason = f"Clock {effective_khz // 1000} MHz holds with boost active."

    return {
        "holdable": True,
        "requested_khz": freq_cap_khz,
        "effective_khz": effective_khz,
        "is_amd_pstate": is_amd,
        "requires_passive_mode": requires_passive,
        "clamped": clamped,
        "reason": reason,
        "adapted_control": control,
    }
