"""Read-only topology discovery (Agent A owns).

General on every machine: discovers CPUs, cores, sockets, SMT siblings,
cpufreq policies, and candidate core classes from per-CPU cpuinfo_max_freq.
Nothing machine-specific is hardcoded — the demo laptop's Zen5/Zen5c split
comes out of the same code path as any other topology.
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class PolicyInfo:
    name: str            # e.g. "policy0"
    cpus: List[int]      # logical CPUs governed
    driver: Optional[str]
    governor: Optional[str]
    min_freq: Optional[int]
    max_freq: Optional[int]
    hw_min_freq: Optional[int]   # cpuinfo_min_freq
    hw_max_freq: Optional[int]   # cpuinfo_max_freq


@dataclass(frozen=True)
class Topology:
    ncpu: int
    cores: Dict[int, List[int]]          # physical core -> logical CPUs (SMT group)
    sockets: Dict[int, List[int]]        # socket -> logical CPUs
    core_of_cpu: Dict[int, int]
    policies: List[PolicyInfo]

    def smt_siblings(self, cpu: int) -> List[int]:
        return [c for c in self.cores[self.core_of_cpu[cpu]] if c != cpu]


@dataclass
class CoreClassMap:
    """Candidate classes from topology reads.

    Classes are keyed by distinct hw_max_freq (cpuinfo_max_freq) values.
    CPU numbering is not evidence — C1 calibration confirms which set is faster.
    """

    classes: Dict[str, List[int]] = field(default_factory=dict)
    hw_max_freq: Dict[str, int] = field(default_factory=dict)

    @property
    def n_classes(self) -> int:
        return len(self.classes)


def _read(path: str) -> Optional[str]:
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def _read_int(path: Optional[int] = None) -> Optional[int]:  # noqa: arg
    ...


def read_int(path: str) -> Optional[int]:
    v = _read(path)
    if v is None:
        return None
    try:
        return int(v)
    except ValueError:
        return None


def read_topology() -> Topology:
    # lscpu -e gives the authoritative core/socket mapping; fall back to sysfs.
    import subprocess

    core_of: Dict[int, int] = {}
    sockets: Dict[int, List[int]] = {}
    try:
        out = subprocess.run(
            ["lscpu", "-e=CPU,CORE,SOCKET,ONLINE"],
            capture_output=True, text=True, timeout=10,
        ).stdout
        for line in out.splitlines():
            parts = line.split()
            if not parts or parts[0] == "CPU":
                continue
            cpu, core, sock, online = int(parts[0]), int(parts[1]), int(parts[2]), parts[3]
            if online != "yes":
                continue
            core_of[cpu] = core
            sockets.setdefault(sock, []).append(cpu)
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        ncpu = os.cpu_count() or 1
        for cpu in range(ncpu):
            core_of[cpu] = cpu
        sockets[0] = list(range(ncpu))

    cores: Dict[int, List[int]] = {}
    for cpu, core in sorted(core_of.items()):
        cores.setdefault(core, []).append(cpu)

    policies = []
    for pdir in sorted(glob.glob("/sys/devices/system/cpu/cpufreq/policy*"), key=_polkey):
        name = os.path.basename(pdir)
        affected = _read(f"{pdir}/affected_cpus")
        cpus = [int(x) for x in affected.split()] if affected else []
        policies.append(PolicyInfo(
            name=name, cpus=cpus,
            driver=_read(f"{pdir}/scaling_driver"),
            governor=_read(f"{pdir}/scaling_governor"),
            min_freq=read_int(f"{pdir}/scaling_min_freq"),
            max_freq=read_int(f"{pdir}/scaling_max_freq"),
            hw_min_freq=read_int(f"{pdir}/cpuinfo_min_freq"),
            hw_max_freq=read_int(f"{pdir}/cpuinfo_max_freq"),
        ))

    return Topology(ncpu=len(core_of), cores=cores, sockets=sockets,
                    core_of_cpu=core_of, policies=policies)


def _polkey(path: str) -> List[int]:
    digits = "".join(ch for ch in os.path.basename(path) if ch.isdigit())
    return [int(digits)]


def read_core_class_map(topo: Topology) -> CoreClassMap:
    """Candidate classes from per-CPU cpuinfo_max_freq via the policies.

    If all policies share one hw_max_freq, there is one class (uniform).
    """
    per_cpu_max: Dict[int, Optional[int]] = {}
    for pol in topo.policies:
        for cpu in pol.cpus:
            per_cpu_max[cpu] = pol.hw_max_freq
    freqs = sorted({f for f in per_cpu_max.values() if f is not None}, reverse=True)
    m = CoreClassMap()
    for i, f in enumerate(freqs):
        key = f"class_{i}_{f}"
        m.classes[key] = sorted(c for c, v in per_cpu_max.items() if v == f)
        m.hw_max_freq[key] = f
    return m


def boost_knob() -> Optional[str]:
    p = "/sys/devices/system/cpu/cpufreq/boost"
    return p if os.path.exists(p) else None
