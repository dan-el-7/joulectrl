#!/usr/bin/env python3
"""C1 calibration run script (Agent A) — single-core stock-only, 2 classes x 5 reps.

Outputs JSON rows to fixtures/real/calibration_c1.json (raw) — median aggregation
done in the commit step. Energy via helper daemon (root-only counter).
"""
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helper.client import HelperClient

KERNEL = Path("workloads/kernel/fixed_compute").resolve()
PARAMS = ["--chunks", "16384", "--iters", "200000"]
CLASSES = {
    "fast": [0, 2, 4, 6, 8, 10, 12, 14],       # Zen 5 (even)
    "efficient": [1, 3, 5, 7, 9, 11, 13, 15],  # Zen 5c (odd)
}
REPS = 5
WRAP = 65_532_610_987


def run_pinned(cpu, params):
    cmd = ["taskset", "-c", str(cpu), str(KERNEL), "--workers", "1", *params]
    t0 = time.monotonic()
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    t1 = time.monotonic()
    out = {}
    for line in p.stdout.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    # "runtime: 8.4752 s (15142.0 chunks/s)" -> runtime + chunks/s from parens
    cps = None
    if "runtime" in out and "(" in out["runtime"]:
        inside = out["runtime"].split("(", 1)[1].split(")", 1)[0]
        try:
            cps = float(inside.split()[0])
        except (ValueError, IndexError):
            pass
    return {
        "runtime_s": round(t1 - t0, 4),
        "kernel_runtime_s": float(out["runtime"].split()[0]) if "runtime" in out else None,
        "checksum": out.get("checksum"),
        "chunks_per_s": cps,
        "returncode": p.returncode,
    }


def main():
    c = HelperClient()
    boot_id = open("/proc/sys/kernel/random/boot_id").read().strip()
    rows = []
    for cname, cpus in CLASSES.items():
        cpu = cpus[0]
        for rep in range(1, REPS + 1):
            e1 = c.read_energy()
            r = run_pinned(cpu, PARAMS)
            e2 = c.read_energy()
            energy_j = None
            if e1.get("ok") and e2.get("ok"):
                d = (e2["uj"] - e1["uj"]) % WRAP
                energy_j = round(d / 1e6, 4)
            rows.append({
                "class": cname, "layout": "C1", "cpus": [cpu], "rep": rep,
                "package_energy_j": energy_j, "boot_id": boot_id,
                "kernel_checksum": r["checksum"], **r,
            })
            print(f"{cname} cpu{cpu} rep{rep}: {r['runtime_s']}s "
                  f"{energy_j}J checksum={r['checksum']}", flush=True)
            time.sleep(1.0)  # settle between reps

    # verify checksum invariance vs default params sanity is done elsewhere;
    # here verify all checksums equal
    checksums = {r["checksum"] for r in rows if r["checksum"]}
    assert len(checksums) == 1, f"checksum drift: {checksums}"

    doc = {
        "schema": "joulectrl.calibration_c1/1",
        "captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "boot_id": boot_id,
        "kernel": "workloads/kernel/fixed_compute (gcc -O3), chunks=16384 iters=200000",
        "params": {"chunks": 16384, "iters": 200000, "reps": REPS, "workers": 1},
        "config": "stock (boost=1, no caps)",
        "rows": rows,
        "summary": {
            cname: {
                "median_runtime_s": statistics.median(r["runtime_s"] for r in rows if r["class"] == cname),
                "median_energy_j": statistics.median(r["package_energy_j"] for r in rows if r["class"] == cname),
                "median_chunks_per_s": statistics.median(r["chunks_per_s"] for r in rows if r["class"] == cname),
            } for cname in CLASSES
        },
    }
    Path("fixtures/real/calibration_c1.json").write_text(json.dumps(doc, indent=2))
    print(json.dumps(doc["summary"], indent=2))


if __name__ == "__main__":
    main()
