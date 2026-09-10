#!/usr/bin/env python3
"""C2-clean: calibration at the REAL control points (post Gate B finding).

This machine's effective control space (verified): per class, stock (boost=1)
and base (boost=0). Capped rows in the first C2 run all measured base.
This run sweeps the true space cleanly with reps:
  {fast, efficient} x {stock, base} x {1, 4} workers x 3 reps = 24 runs.
Output: fixtures/real/calibration_c2_effective.json
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
CLASSES = {"fast": [0, 2, 4, 6], "efficient": [1, 3, 5, 7]}
REPS = 3


def run_pinned(cpus, workers, chunks):
    mask = ",".join(str(c) for c in cpus)
    cmd = ["taskset", "-c", mask, str(KERNEL), "--workers", str(workers),
           "--chunks", str(chunks), "--iters", "200000"]
    t0 = time.monotonic()
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
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

    def beat():
        c.heartbeat()

    try:
        for cname, cpus in CLASSES.items():
            for boost in (True, False):
                r = c.apply_configuration({"boost": boost})
                assert r["ok"], r
                beat()
                time.sleep(0.5)  # settle after control change
                label = "stock" if boost else "base"
                for workers in (1, 4):
                    # single worker pinned to first core; 4 workers = full class layout
                    pin = [cpus[0]] if workers == 1 else cpus
                    # scale work so point durations are comparable: 16384 for 1w, 32768 for 4w
                    chunks = 16384 if workers == 1 else 32768
                    for rep in range(1, REPS + 1):
                        beat()
                        e1 = c.read_energy()
                        rr = run_pinned(pin, workers, chunks)
                        e2 = c.read_energy()
                        ej = ((e2["uj"] - e1["uj"]) % WRAP) / 1e6 if e1.get("ok") and e2.get("ok") else None
                        rows.append({
                            "class": cname, "control": label, "boost": int(boost),
                            "workers": workers, "cpus": pin, "chunks": chunks,
                            "rep": rep, "runtime_s": rr["runtime_s"],
                            "package_energy_j": round(ej, 4) if ej else None,
                            "kernel_checksum": rr["checksum"], "boot_id": boot_id,
                        })
                        print(f"{cname} {label} w{workers} rep{rep}: {rr['runtime_s']}s "
                              f"{rows[-1]['package_energy_j']}J", flush=True)
                        time.sleep(0.4)
    finally:
        rr = c.restore()
        print("restore:", rr["ok"], rr.get("mismatches", []), flush=True)
        assert rr["ok"]
        c.end_session()

    checksums = {r["kernel_checksum"] for r in rows if r["kernel_checksum"]}
    assert len(checksums) == 2, f"expected 2 checksums (1w/4w chunk sizes), got {checksums}"
    summary = {}
    for cname in CLASSES:
        for label in ("stock", "base"):
            for workers in (1, 4):
                pts = [r for r in rows if r["class"] == cname
                       and r["control"] == label and r["workers"] == workers]
                key = f"{label}_w{workers}"
                summary.setdefault(cname, {})[key] = {
                    "median_runtime_s": statistics.median(p["runtime_s"] for p in pts),
                    "median_energy_j": statistics.median(p["package_energy_j"] for p in pts),
                    "n": len(pts),
                }
    doc = {
        "schema": "joulectrl.calibration_c2_effective/1",
        "captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "boot_id": boot_id,
        "kernel": "workloads/kernel/fixed_compute, iters=200000, chunks 16384(1w)/32768(4w)",
        "basis": "Gate B finding: only 2 binding control points per class on this machine (stock/base); see calibration_c2.json gate_b_findings",
        "rows": rows,
        "summary": summary,
    }
    Path("fixtures/real/calibration_c2_effective.json").write_text(json.dumps(doc, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
