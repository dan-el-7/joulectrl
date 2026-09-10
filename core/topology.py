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


def discover_freq_limits(topo: Optional[Topology] = None) -> tuple[int, int]:
    """Discover hardware minimum frequency cap and nominal/base frequency clamp (in kHz).

    Returns:
        (cap_min_khz, cap_max_khz)
    """
    if topo is None:
        try:
            topo = read_topology()
        except Exception:
            topo = None

    cap_min = 600000
    if topo and topo.policies:
        hw_min_freqs = [p.hw_min_freq for p in topo.policies if p.hw_min_freq]
        if hw_min_freqs:
            cap_min = min(hw_min_freqs)
        else:
            min_freqs = [p.min_freq for p in topo.policies if p.min_freq]
            if min_freqs:
                cap_min = min(min_freqs)

    cap_max = None
    # 1. ACPI CPPC nominal_freq (in MHz on modern AMD and Intel)
    cppc_files = glob.glob("/sys/devices/system/cpu/cpu*/acpi_cppc/nominal_freq")
    if cppc_files:
        try:
            with open(cppc_files[0]) as f:
                val = int(f.read().strip())
                if val > 0:
                    cap_max = val * 1000
        except Exception:
            pass

    # 2. Intel cpufreq base_frequency (in kHz)
    if not cap_max:
        base_files = glob.glob("/sys/devices/system/cpu/cpufreq/policy*/base_frequency")
        if base_files:
            try:
                with open(base_files[0]) as f:
                    val = int(f.read().strip())
                    if val > 0:
                        cap_max = val
            except Exception:
                pass

    # 3. Fallback from policy scaling_max_freq or hw_max_freq
    if not cap_max and topo and topo.policies:
        hw_max_freqs = [p.hw_max_freq for p in topo.policies if p.hw_max_freq]
        if hw_max_freqs:
            cap_max = min(hw_max_freqs)

    if not cap_max:
        cap_max = 2000000

    if cap_min >= cap_max:
        cap_min = max(300000, cap_max // 3)

    return cap_min, cap_max


def discover_hardware_classes(topo: Optional[Topology] = None) -> List[Dict[str, Any]]:
    """Dynamically discover available execution classes and thread layouts for calibration.

    All returned configurations use invariant 65,536 chunks for constant compute workload.
    """
    if topo is None:
        try:
            topo = read_topology()
        except Exception:
            topo = None

    if not topo or topo.ncpu <= 0:
        ncpu = os.cpu_count() or 1
        return [{
            "class": "all_logical",
            "display": f"All Cores ({ncpu} threads)",
            "cpus": list(range(ncpu)),
            "workers": ncpu,
            "chunks": 65536,
        }]

    classes: List[Dict[str, Any]] = []

    # 1. All logical threads (SMT)
    classes.append({
        "class": "all_logical",
        "display": f"All Cores ({topo.ncpu} threads)",
        "cpus": list(range(topo.ncpu)),
        "workers": topo.ncpu,
        "chunks": 65536,
    })

    # 2. Heterogeneous core classes (if available)
    cmap = read_core_class_map(topo)
    if cmap.n_classes > 1:
        sorted_cls = sorted(cmap.classes.items(), key=lambda x: cmap.hw_max_freq.get(x[0], 0), reverse=True)
        # Class 0: Fast / P-cores
        fast_key, fast_cpus = sorted_cls[0]
        fast_freq = cmap.hw_max_freq.get(fast_key)
        fast_disp = f"Fast Cores ({len(fast_cpus)} threads, ≤{fast_freq/1e6:.2f} GHz)" if fast_freq else f"Fast Cores ({len(fast_cpus)} threads)"
        classes.append({
            "class": "fast",
            "display": fast_disp,
            "cpus": fast_cpus,
            "workers": len(fast_cpus),
            "chunks": 65536,
        })
        # Class 1: Efficient / E-cores
        eff_key, eff_cpus = sorted_cls[1]
        eff_freq = cmap.hw_max_freq.get(eff_key)
        eff_disp = f"Eco Cores ({len(eff_cpus)} threads, ≤{eff_freq/1e6:.2f} GHz)" if eff_freq else f"Eco Cores ({len(eff_cpus)} threads)"
        classes.append({
            "class": "efficient",
            "display": eff_disp,
            "cpus": eff_cpus,
            "workers": len(eff_cpus),
            "chunks": 65536,
        })
    elif topo.ncpu > len(topo.cores):
        # Homogeneous CPU with SMT: add all_physical (1 thread per core)
        phys_cpus = [topo.cores[c][0] for c in sorted(topo.cores.keys())]
        classes.append({
            "class": "all_physical",
            "display": f"Physical Cores ({len(phys_cpus)} cores)",
            "cpus": phys_cpus,
            "workers": len(phys_cpus),
            "chunks": 65536,
        })

    return classes

