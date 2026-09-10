#!/usr/bin/env python3
"""Gate 4 pre-demo controls re-verification (Agent A).

Re-runs the Gate B checks on the real machine and records conditions
(AC, tuned profile, thermal) — the "controls re-verified, conditions noted"
Gate 4 A-item. Fast (~30 s), bracketed with [measuring] when run for record.

Checks:
  1. energy counter advances
  2. stock frequencies + boost as expected
  3. cap binds under boost=0 (actual cur_freq under load, not just readback)
  4. sub-base cap still ignored (control-space assumption holds)
  5. restore verified zero-mismatch
"""
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from helper.client import HelperClient

WRAP = 65_532_610_987
BASE = "/sys/devices/system/cpu/cpufreq"


def busy(cpu=0, dur=2.0):
    return subprocess.Popen(["taskset", "-c", str(cpu), "sha256sum", "/dev/zero"],
                            stdout=subprocess.DEVNULL)


def read(path):
    try:
        return open(path).read().strip()
    except OSError:
        return None


def main():
    c = HelperClient()
    report = {"captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "boot_id": read("/proc/sys/kernel/random/boot_id"),
              "ac_online": read("/sys/class/power_supply/ACAD/online"),
              "tuned_profile": None, "checks": {}}

    tp = subprocess.run(["tuned-adm", "active"], capture_output=True, text=True)
    for line in tp.stdout.splitlines():
        if "active profile" in line:
            report["tuned_profile"] = line.split(":", 1)[1].strip()

    # 1. energy advances
    e1 = c.read_energy(); time.sleep(1.0); e2 = c.read_energy()
    report["checks"]["energy_advances"] = bool(
        e1.get("ok") and e2.get("ok") and ((e2["uj"] - e1["uj"]) % WRAP) > 0)

    # 2. stock state
    report["checks"]["stock_boost"] = read(f"{BASE}/boost") == "1"
    report["checks"]["stock_p0_max"] = read(f"{BASE}/policy0/scaling_max_freq")
    report["checks"]["stock_p1_max"] = read(f"{BASE}/policy1/scaling_max_freq")

    # 3+4. cap binding under boost=0 with load evidence
    assert c.begin_session()["ok"]
    try:
        r = c.apply_configuration({"boost": False,
                                   "policy_freq_caps_khz": {"policy0": 2000000}})
        time.sleep(0.5)
        p = busy()
        time.sleep(1.5)
        cur = int(read(f"{BASE}/policy0/scaling_cur_freq"))
        p.kill(); p.wait()
        report["checks"]["cap_binds_boost0_2ghz"] = cur <= 2_100_000
        report["checks"]["boost0_cur_khz"] = cur

        # sub-base still ignored?
        r = c.apply_configuration({"policy_freq_caps_khz": {"policy0": 800000}})
        time.sleep(0.5)
        p = busy()
        time.sleep(1.5)
        cur2 = int(read(f"{BASE}/policy0/scaling_cur_freq"))
        p.kill(); p.wait()
        report["checks"]["subbase_cap_still_ignored"] = cur2 > 1_900_000
        report["checks"]["subbase_cur_khz"] = cur2
    finally:
        rr = c.restore()
        report["checks"]["restore_ok"] = rr["ok"]
        report["checks"]["restore_mismatches"] = rr.get("mismatches", [])
        c.end_session()

    report["checks"]["post_boost"] = read(f"{BASE}/boost")
    ok = (report["checks"]["energy_advances"] and report["checks"]["stock_boost"]
          and report["checks"]["cap_binds_boost0_2ghz"]
          and report["checks"]["subbase_cap_still_ignored"]
          and report["checks"]["restore_ok"])
    print(json.dumps(report, indent=2))
    print("RE-VERIFY:", "PASS" if ok else "FAIL")
    Path("fixtures/real/controls_reverify.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
