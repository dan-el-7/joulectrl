"""Capability discovery for `joulectrl doctor` (Agent A owns).

Read-only. Produces a CapabilityReport dict (machine facts only — no product
assumptions). The privileged parts (energy counter advance, cap actual-effect)
are verified out-of-band and folded into the report by the caller.
"""

from __future__ import annotations

import glob
from typing import Dict, List, Optional

from core.topology import (
    Topology, read_topology, read_core_class_map, boost_knob, read_int, _read
)


def find_powercap_energy_paths() -> List[str]:
    """All energy_uj counters under /sys/class/powercap (deduplicated)."""
    seen = set()
    paths = []
    for p in sorted(glob.glob("/sys/class/powercap/*/energy_uj")):
        real = str(p)
        if real not in seen:
            seen.add(real)
            paths.append(p)
    return paths


def find_package_energy_paths() -> List[Dict]:
    """powercap domains whose name indicates a whole package."""
    out = []
    for e in find_powercap_energy_paths():
        base = e.rsplit("/", 1)[0]
        name = _read(f"{base}/name") or ""
        if "package" in name.lower():
            out.append({
                "path": e,
                "domain": name,
                "max_energy_range_uj": read_int(f"{base}/max_energy_range_uj"),
            })
    return out


def epp_available(policy_dir: str) -> List[str]:
    v = _read(f"{policy_dir}/energy_performance_available_preferences")
    return v.split() if v else []


def detect_pm_daemons() -> Dict[str, Optional[str]]:
    """Detect power-management daemons that may fight our control writes."""
    import subprocess
    found: Dict[str, Optional[str]] = {}
    try:
        out = subprocess.run(["systemctl", "list-units", "--state=running",
                              "--no-legend", "--plain"],
                             capture_output=True, text=True, timeout=10).stdout
        for daemon in ("tuned", "tuned-ppd", "power-profiles-daemon",
                       "nvidia-powerd", "upowerd"):
            hit = next((l.split()[0] for l in out.splitlines()
                        if l.strip().startswith(daemon)), None)
            found[daemon] = hit
    except (OSError, subprocess.SubprocessError):
        found = {d: None for d in ("tuned", "tuned-ppd", "power-profiles-daemon",
                                   "nvidia-powerd", "upowerd")}
    try:
        out = subprocess.run(["tuned-adm", "active"], capture_output=True,
                             text=True, timeout=10).stdout
        for line in out.splitlines():
            if "active profile" in line:
                found["tuned_profile"] = line.split(":", 1)[1].strip()
    except (OSError, subprocess.SubprocessError):
        found["tuned_profile"] = None
    return found


def capability_report() -> Dict:
    """Assemble the read-only capability report (JSON-serializable dict)."""
    topo: Topology = read_topology()
    classes = read_core_class_map(topo)
    pkg = find_package_energy_paths()
    # readability of the first package counter (None if unreadable)
    energy_readable = None
    energy_backend = None
    if pkg:
        e = pkg[0]["path"]
        try:
            with open(e) as f:
                int(f.read().strip())
            energy_readable = "unprivileged"
            energy_backend = e
        except PermissionError:
            energy_readable = "permission_required"
            energy_backend = e
        except OSError:
            energy_readable = "unavailable"

    drivers = {p.driver for p in topo.policies if p.driver}
    governors = {p.governor for p in topo.policies if p.governor}
    epp = epp_available("/sys/devices/system/cpu/cpufreq/policy0") if topo.policies else []

    return {
        "cpu": {
            "model": _read("/proc/cpuinfo").split("model name")[1].split("\n")[0].strip().lstrip(":\t ") if "model name" in (_read("/proc/cpuinfo") or "") else None,
            "ncpu": topo.ncpu,
            "n_cores": len(topo.cores),
            "sockets": {str(s): cpus for s, cpus in topo.sockets.items()},
            "smt_groups": {str(c): cpus for c, cpus in topo.cores.items()},
        },
        "cpufreq": {
            "n_policies": len(topo.policies),
            "per_cpu_policies": len(topo.policies) == topo.ncpu,
            "drivers": sorted(drivers),
            "governors": sorted(governors),
            "boost_knob": boost_knob(),
        },
        "core_classes": {
            "available": classes.n_classes > 1,
            "n_classes": classes.n_classes,
            "classes": {k: {"cpus": v, "hw_max_freq": classes.hw_max_freq[k]}
                        for k, v in classes.classes.items()},
            "source": "per-cpu cpuinfo_max_freq",
        },
        "energy": {
            "package_paths": pkg,
            "readable": energy_readable,
            "backend": energy_backend,
        },
        "epp": {
            "available_values": epp,
            "usable": len(epp) > 1,
        },
        "pm_daemons": detect_pm_daemons(),
    }
