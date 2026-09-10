#!/usr/bin/env python3
"""Co-sign test: B's WatchDetector against real hardware + helper energy reads.

Protocol (AGENTS.md §6b co-sign): learn idle baseline ~30 s, then run a known
~20 s workload (fixed_compute, 4 workers, no controls — watch is read-only),
and compare detector-detected runtime/energy vs measured truth.
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core.watch import WatchDetector
from helper.client import HelperClient

WRAP = 65_532_610_987
KERNEL = Path("workloads/kernel/fixed_compute").resolve()


def main():
    c = HelperClient()
    det = WatchDetector(baseline_window_s=30.0, onset_s=3.0,
                        idle_grace_s=10.0, poll_interval_s=1.0,
                        energy_range_uj=WRAP)

    def power_now(e_prev=None):
        r = c.read_energy()
        return r

    print("phase 1: learning idle baseline (30 s)...", flush=True)
    t_start = time.monotonic()
    prev_uj, prev_t = None, None
    launched = False
    proc = None
    truth_t0 = truth_t1 = None
    truth_e0 = truth_e1 = None
    while time.monotonic() - t_start < 110:
        r = c.read_energy()
        now = time.monotonic()
        uj = r.get("uj") if r.get("ok") else None
        power_w = None
        if uj is not None and prev_uj is not None:
            dt = now - prev_t
            power_w = ((uj - prev_uj) % WRAP) / 1e6 / dt if dt > 0 else None
        if power_w is not None:
            seg = det.observe(power_w, uj, now)
            if seg:
                print(f"SEGMENT CLOSED: runtime={seg.runtime_s:.2f}s energy={seg.energy_j}J "
                      f"baseline={det.baseline_w:.2f}W spread={det.spread_w:.2f}W", flush=True)
                # record the first closed segment as the detected task window
                detected = seg
                break
        prev_uj, prev_t = uj, now

        # at t=40s (10 s after baseline window), launch the 20 s workload
        elapsed = now - t_start
        if not launched and elapsed > 40:
            truth_e0 = c.read_energy()
            truth_t0 = time.monotonic()
            proc = subprocess.Popen(
                ["taskset", "-c", "0,2,4,6", str(KERNEL), "--workers", "4",
                 "--chunks", "65536", "--iters", "200000"],
                stdout=subprocess.DEVNULL)
            launched = True
            print(f"phase 2: workload launched at t={elapsed:.0f}s", flush=True)
        if launched and proc is not None and proc.poll() is not None and truth_t1 is None:
            truth_t1 = time.monotonic()
            truth_e1 = c.read_energy()
            print(f"phase 2: workload done at t={now - t_start:.0f}s "
                  f"(true runtime {truth_t1 - truth_t0:.2f}s)", flush=True)
        time.sleep(1.0)
    else:
        print("TIMEOUT: no segment closed")
        sys.exit(1)

    truth_runtime = truth_t1 - truth_t0
    truth_energy = ((truth_e1["uj"] - truth_e0["uj"]) % WRAP) / 1e6
    det_runtime = detected.runtime_s
    det_energy = detected.energy_j
    rt_err = det_runtime - truth_runtime
    e_err = (det_energy - truth_energy) if det_energy is not None else None
    print(f"true: {truth_runtime:.2f}s / {truth_energy:.1f}J")
    print(f"detected: {det_runtime:.2f}s / {det_energy}J")
    print(f"error: runtime {rt_err:+.2f}s (poll uncertainty ±1s), energy {e_err}")
    # co-sign criteria: |runtime error| <= onset+poll+grace slack (backdating should
    # make it much tighter), energy within 25% (boundary attribution differs)
    ok = abs(rt_err) <= 5.0 and (e_err is not None and abs(e_err) <= 0.25 * truth_energy)
    print("CO-SIGN:", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    main()
