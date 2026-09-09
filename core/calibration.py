"""Calibration orchestration (Agent A owns): C1 single-core + C2 dense sweep.

C1 (single-core, stock only): kernel pinned via taskset to one core from each
class, >=5 reps, quiet mode. One row per class: median runtime, package
energy, avg watts, work/sec. Validates the class map empirically; gives the
baseline C2's scaling-efficiency number divides by.

C2 (dense sweep): same kernel at each class's full-physical-core layout
(4 workers, one SMT sibling each), stock row first, then N evenly spaced cap
points (tier 2 ladder on this machine: 623377..2000000 kHz, boost=0).

All energy reads go through the helper daemon (root-only counter).
"""

from __future__ import annotations

import json
import statistics
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional

from helper.client import HelperClient

KERNEL = Path(__file__).resolve().parent.parent / "workloads" / "kernel" / "fixed_compute"
C1_PARAMS = ["--chunks", "16384", "--iters", "200000"]
C2_PARAMS = ["--chunks", "32768", "--iters", "200000"]
WRAP_RANGE_UJ = 65_532_610_987  # demo laptop package-0 counter range (capability report)


def _mask_of(cpus: List[int]) -> str:
    return ",".join(str(c) for c in cpus)


def _run_kernel(cpus: List[int], workers: int, params: List[str],
                timeout: float = 300.0) -> Dict:
    """Run the pinned kernel; return runtime + parsed output. Monotonic clock."""
    cmd = ["taskset", "-c", _mask_of(cpus), str(KERNEL),
           "--workers", str(workers), *params]
    t0 = time.monotonic()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    t1 = time.monotonic()
    out = {}
    for line in proc.stdout.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return {
        "runtime_s": t1 - t0,
        "wall_runtime_s": float(out.get("runtime", "0").split()[0]) if out.get("runtime") else None,
        "checksum": out.get("checksum"),
        "chunks_per_s": float(out["chunks/s"].split()[0]) if "chunks/s" in out else None,
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-200:],
    }


def _energy_between(c: HelperClient, r1: Dict, r2: Dict) -> Optional[float]:
    """Wrap-safe energy delta between two helper read_energy results (uj->J)."""
    if not (r1.get("ok") and r2.get("ok")):
        return None
    d = (r2["uj"] - r1["uj"]) % WRAP_RANGE_UJ
    return d / 1e6


def calibration_c1(classes: Dict[str, List[int]], reps: int = 5,
                   helper: Optional[HelperClient] = None) -> List[Dict]:
    """Single-core stock-only calibration, one row per class.

    classes: {"fast": [cpus...], "efficient": [cpus...]} — layout candidates.
    Pins to exactly one logical CPU per class, workers=1.
    Energy brackets the run: read_energy before launch and after termination.
    """
    c = helper or HelperClient()
    rows = []
    for cname, cpus in sorted(classes.items()):
        mask = [cpus[0]]
        for rep in range(1, reps + 1):
            e1 = c.read_energy()
            r = _run_kernel(mask, 1, C1_PARAMS)
            e2 = c.read_energy()
            energy_j = _energy_between(c, e1, e2)
            rows.append({"class": cname, "layout": "C1", "cpus": mask,
                         "rep": rep, "package_energy_j": energy_j, **r})
    return rows
