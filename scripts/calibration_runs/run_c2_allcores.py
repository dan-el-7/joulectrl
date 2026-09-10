#!/usr/bin/env python3
"""C2 all-cores calibration (Agent A) — fills the layout-B/C gap in the curve.

The effective calibration (calibration_c2_effective.json) covers 1w and 4w
(one class's physical cores). This run adds the mixed-class layouts:
  all8  = CPUs 0-7   (one worker per physical core, both classes mixed)
  all16 = CPUs 0-15  (all logical CPUs incl. SMT siblings)
x {stock (boost=1), base (boost=0)} x 3 reps.

Per-worker work is held equal to the 4w C2 points (32768 chunks / 4 workers),
so chunks scale with workers: 8w -> 65536, 16w -> 131072. The kernel's
checksum invariance across worker counts is a verified fact (§9).
Energy brackets each run via the helper daemon; restore in finally.
Output: fixtures/real/calibration_c2_allcores.json
"""
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from helper.client import HelperClient

KERNEL = (REPO_ROOT / "workloads/kernel/fixed_compute").resolve()
WRAP = 65_532_610_987
LAYOUTS = {
    "all8": {"cpus": list(range(8)), "workers": 8, "chunks": 65536},
    "all16": {"cpus": list(range(16)), "workers": 16, "chunks": 131072},
}
REPS = 3
OUT = Path("fixtures/real/calibration_c2_allcores.json")


def run_pinned(cpus, workers, chunks):
    mask = ",".join(str(c) for c in cpus)
    cmd = ["taskset", "-c", mask, str(KERNEL), "--workers", str(workers),
           "--chunks", str(chunks), "--iters", "200000"]
    t0 = time.monotonic()
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    t1 = time.monotonic()
    out = {}
    for line in p.stdout.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return {"runtime_s": round(t1 - t0, 4), "checksum": out.get("checksum"),
            "returncode": p.returncode}


def main():
    c = HelperClient()
    boot_id = open("/proc/sys/kernel/random/boot_id").read().strip()
    assert c.begin_session()["ok"]
    rows = []

    try:
        for lname, lay in LAYOUTS.items():
            for boost in (True, False):
                r = c.apply_configuration({"boost": boost})
                assert r["ok"], r
                c.heartbeat()
                time.sleep(0.5)  # settle after control change
                label = "stock" if boost else "base"
                for rep in range(1, REPS + 1):
                    c.heartbeat()
                    e1 = c.read_energy()
                    rr = run_pinned(lay["cpus"], lay["workers"], lay["chunks"])
                    e2 = c.read_energy()
                    ej = ((e2["uj"] - e1["uj"]) % WRAP) / 1e6 if e1.get("ok") and e2.get("ok") else None
                    rows.append({
                        "layout": lname, "control": label, "boost": int(boost),
                        "workers": lay["workers"], "cpus": lay["cpus"],
                        "chunks": lay["chunks"], "rep": rep,
                        "runtime_s": rr["runtime_s"],
                        "package_energy_j": round(ej, 4) if ej else None,
                        "kernel_checksum": rr["checksum"], "boot_id": boot_id,
                    })
                    print(f"{lname} {label} rep{rep}: {rr['runtime_s']}s "
                          f"{rows[-1]['package_energy_j']}J cs={rr['checksum']}", flush=True)
                    time.sleep(0.4)
    finally:
        rr = c.restore()
        print("restore:", rr["ok"], rr.get("mismatches", []), flush=True)
        assert rr["ok"]
        c.end_session()

    checksums = {r["kernel_checksum"] for r in rows if r["kernel_checksum"]}
    assert len(checksums) == 2, f"expected 2 checksums (8w/16w chunk sizes), got {checksums}"
    summary = {}
    for lname in LAYOUTS:
        for label in ("stock", "base"):
            pts = [r for r in rows if r["layout"] == lname and r["control"] == label]
            summary.setdefault(lname, {})[label] = {
                "median_runtime_s": statistics.median(p["runtime_s"] for p in pts),
                "median_energy_j": statistics.median(p["package_energy_j"] for p in pts),
                "n": len(pts),
            }
    doc = {
        "schema": "joulectrl.calibration_c2_allcores/1",
        "captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "boot_id": boot_id,
        "kernel": "workloads/kernel/fixed_compute, iters=200000, chunks 65536(8w)/131072(16w), per-worker work equal to c2_effective 4w points",
        "basis": "All-cores layouts (mixed-class) at the 2 effective control points per class; complements calibration_c2_effective.json (1w/4w single-class)",
        "rows": rows,
        "summary": summary,
    }
    OUT.write_text(json.dumps(doc, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
