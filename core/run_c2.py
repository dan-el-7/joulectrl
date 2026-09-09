#!/usr/bin/env python3
"""C2 dense calibration sweep (Agent A) — the performance-per-watt curve.

Per class (fast = Zen5 CPUs 0,2,4,6 / efficient = Zen5c CPUs 1,3,5,7):
  1. Stock row first (boost=1, no caps) -> scaling efficiency baseline.
  2. Dense cap sweep, tier 2 ladder (continuous range, no discrete list on this
     machine): N evenly spaced caps in [623377..2000000] kHz with boost=0,
     written per-policy (all 16 policies for the active class's CPUs), readback
     verified per point.

4 workers, one SMT sibling each (one per physical core of the class).
Energy brackets each run via the helper daemon. Every point: requested +
accepted control recorded. Output: fixtures/real/calibration_c2.json.

Budget-aware: N points per class from CLI arg (default 7); each point ~10-15 s
kernel + settle. Total ~ (N+1) * 2 classes * ~15s ≈ 4 min at N=7.
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
PARAMS = ["--chunks", "32768", "--iters", "200000"]
WRAP = 65_532_610_987
CLASSES = {
    "fast": [0, 2, 4, 6],
    "efficient": [1, 3, 5, 7],
}
CAP_MIN_KHZ = 623377
CAP_MAX_KHZ = 2000000  # boost=0 cpuinfo clamp (verified machine fact)
N_POINTS = int(sys.argv[1]) if len(sys.argv) > 1 else 7
REPS = 1  # shape-finding pass; second rep if budget allows


def run_pinned(cpus, workers, params):
    mask = ",".join(str(c) for c in cpus)
    cmd = ["taskset", "-c", mask, str(KERNEL), "--workers", str(workers), *params]
    t0 = time.monotonic()
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    t1 = time.monotonic()
    out = {}
    for line in p.stdout.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return {
        "runtime_s": round(t1 - t0, 4),
        "kernel_runtime_s": float(out["runtime"].split()[0]) if "runtime" in out else None,
        "checksum": out.get("checksum"),
        "returncode": p.returncode,
    }


def cap_ladder(n):
    if n == 1:
        return [CAP_MAX_KHZ]
    step = (CAP_MAX_KHZ - CAP_MIN_KHZ) / (n - 1)
    return [round(CAP_MIN_KHZ + i * step) for i in range(n)]


def main():
    c = HelperClient()
    boot_id = open("/proc/sys/kernel/random/boot_id").read().strip()
    assert c.begin_session()["ok"], "helper lease"
    rows = []
    try:
        for cname, core_cpus in CLASSES.items():
            # ---- stock row (boost=1, no caps) ----
            for rep in range(1, REPS + 1):
                e1 = c.read_energy()
                r = run_pinned(core_cpus, 4, PARAMS)
                e2 = c.read_energy()
                ej = ((e2["uj"] - e1["uj"]) % WRAP) / 1e6 if e1.get("ok") and e2.get("ok") else None
                rows.append({"class": cname, "layout": "C2", "cpus": core_cpus,
                             "workers": 4, "rep": rep,
                             "requested_control": {"boost": 1, "cap_khz": None},
                             "accepted_control": {"boost": 1, "cap_khz": None},
                             "package_energy_j": round(ej, 4) if ej else None,
                             "boot_id": boot_id, "kernel_checksum": r["checksum"], **r})
                print(f"{cname} STOCK rep{rep}: {r['runtime_s']}s {rows[-1]['package_energy_j']}J", flush=True)
                time.sleep(1.0)

            # ---- dense cap sweep (boost=0) ----
            for cap in cap_ladder(N_POINTS):
                req = {"boost": False,
                       "policy_freq_caps_khz": {f"policy{cpu}": cap for cpu in core_cpus}}
                ap = c.apply_configuration(req)
                if not ap.get("ok"):
                    print(f"apply failed at {cap}: {ap}", flush=True)
                    continue
                accepted = ap["applied"]
                time.sleep(0.5)  # settle after control change
                for rep in range(1, REPS + 1):
                    e1 = c.read_energy()
                    r = run_pinned(core_cpus, 4, PARAMS)
                    e2 = c.read_energy()
                    ej = ((e2["uj"] - e1["uj"]) % WRAP) / 1e6 if e1.get("ok") and e2.get("ok") else None
                    rows.append({"class": cname, "layout": "C2", "cpus": core_cpus,
                                 "workers": 4, "rep": rep,
                                 "requested_control": {"boost": False, "cap_khz": cap},
                                 "accepted_control": {"boost": accepted.get("boost"),
                                                      "cap_khz": accepted.get(f"policy{core_cpus[0]}/scaling_max_freq")},
                                 "package_energy_j": round(ej, 4) if ej else None,
                                 "boot_id": boot_id, "kernel_checksum": r["checksum"], **r})
                    print(f"{cname} cap={cap/1e6:.2f}GHz rep{rep}: {r['runtime_s']}s {rows[-1]['package_energy_j']}J", flush=True)
                    time.sleep(0.5)
    finally:
        rr = c.restore()
        print("restore:", rr["ok"], rr.get("mismatches", []), flush=True)
        assert rr["ok"], f"RESTORE FAILED: {rr}"
        c.end_session()

    checksums = {r["checksum"] for r in rows if r["checksum"]}
    assert len(checksums) == 1, f"checksum drift: {checksums}"
    # scaling efficiency vs C1
    c1 = json.load(open("fixtures/real/calibration_c1.json"))
    summary = {}
    for cname in CLASSES:
        pts = [r for r in rows if r["class"] == cname]
        stock = [r for r in pts if r["requested_control"]["boost"] == 1]
        c1_thr = c1["summary"][cname]["median_chunks_per_s"]
        summary[cname] = {
            "stock": {"runtime_s": stock[0]["runtime_s"],
                      "energy_j": stock[0]["package_energy_j"]},
            "scaling_efficiency": round(
                (32768 / stock[0]["runtime_s"]) / (4 * c1_thr), 4),
            "n_points": len(pts) - 1,
        }
    doc = {
        "schema": "joulectrl.calibration_c2/1",
        "captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "boot_id": boot_id,
        "kernel": "workloads/kernel/fixed_compute (gcc -O3), chunks=32768 iters=200000, 4 workers",
        "params": {"chunks": 32768, "iters": 200000, "workers": 4,
                   "n_cap_points": N_POINTS, "reps": REPS,
                   "cap_range_khz": [CAP_MIN_KHZ, CAP_MAX_KHZ], "boost": 0},
        "rows": rows,
        "summary": summary,
    }
    Path("fixtures/real/calibration_c2.json").write_text(json.dumps(doc, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
