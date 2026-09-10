#!/usr/bin/env python3
"""Auto-Pilot Mode vs Default Stock: Fair, Unrigged End-to-End Comparison.

Executes an identical multi-stage active developer workload under:
  1. Default (Stock Boost 5.09 GHz, Auto-Pilot Disarmed)
  2. Auto-Pilot Mode (Dynamic Sweet-Spot Clamping, Target ~20% Energy Savings)

Measures exact physical AMD RAPL package energy counters (Joules) and high-resolution
wall-clock timestamps across all stages.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from helper.client import HelperClient

API_BASE = "http://127.0.0.1:8127"
WRAP_ENERGY_UJ = 65_532_610_987


def api_post(endpoint: str, payload: dict | None = None) -> dict:
    url = f"{API_BASE}{endpoint}"
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_get(endpoint: str) -> dict:
    url = f"{API_BASE}{endpoint}"
    with urllib.request.urlopen(url, timeout=10.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


def delta_energy_j(start_uj: int, end_uj: int) -> float:
    diff = end_uj - start_uj
    if diff < 0:
        diff += WRAP_ENERGY_UJ
    return diff / 1e6


def run_stage(name: str, fn, helper: HelperClient) -> dict[str, Any]:
    e_start = helper.read_energy()["uj"]
    t_start = time.perf_counter()
    fn()
    t_end = time.perf_counter()
    e_end = helper.read_energy()["uj"]

    duration_s = t_end - t_start
    joules = delta_energy_j(e_start, e_end)
    power_w = joules / duration_s if duration_s > 0 else 0.0

    return {
        "name": name,
        "duration_s": round(duration_s, 3),
        "energy_j": round(joules, 2),
        "power_w": round(power_w, 2),
    }


def execute_developer_workload(label: str, helper: HelperClient) -> dict[str, Any]:
    print(f"\n[{label}] Starting multi-stage developer workload...")
    stages = []

    # 1. Clean build directory first (not timed, ensures identical compile scope)
    subprocess.run(
        ["make", "-C", "workloads/build_target/zstd", "clean"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(REPO_ROOT),
    )

    # Stage 1: Parallel C++ Compilation (8 threads)
    print(f"[{label}] Stage 1: Parallel C++ Compilation (zstd -j8)...")
    st1 = run_stage(
        "Parallel Compilation (zstd -j8)",
        lambda: subprocess.run(
            ["make", "-C", "workloads/build_target/zstd", "-j8"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(REPO_ROOT),
            check=True,
        ),
        helper,
    )
    stages.append(st1)
    print(f"    -> Time: {st1['duration_s']}s | Energy: {st1['energy_j']} J | Power: {st1['power_w']} W")

    # Stage 2: Developer Think Time (Reading build logs / planning)
    print(f"[{label}] Stage 2: Think / Idle Time (Reading build logs, 4.0s)...")
    st2 = run_stage(
        "Developer Think Time (Idle 4s)",
        lambda: time.sleep(4.0),
        helper,
    )
    stages.append(st2)
    print(f"    -> Time: {st2['duration_s']}s | Energy: {st2['energy_j']} J | Power: {st2['power_w']} W")

    # Stage 3: Arithmetic Crunch Kernel (16 workers, parallel compute)
    print(f"[{label}] Stage 3: Arithmetic Compute Kernel (16 workers, fixed compute)...")
    st3 = run_stage(
        "Arithmetic Compute Kernel (16 workers)",
        lambda: subprocess.run(
            ["./workloads/kernel/fixed_compute", "-w", "16", "-i", "5000000"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(REPO_ROOT),
            check=True,
        ),
        helper,
    )
    stages.append(st3)
    print(f"    -> Time: {st3['duration_s']}s | Energy: {st3['energy_j']} J | Power: {st3['power_w']} W")

    # Stage 4: Test Review Pause (3.0s)
    print(f"[{label}] Stage 4: Test Review Pause (Idle 3s)...")
    st4 = run_stage(
        "Review Pause (Idle 3s)",
        lambda: time.sleep(3.0),
        helper,
    )
    stages.append(st4)
    print(f"    -> Time: {st4['duration_s']}s | Energy: {st4['energy_j']} J | Power: {st4['power_w']} W")

    # Stage 5: Compression Benchmark (zstd benchmark on binary)
    print(f"[{label}] Stage 5: Compression Benchmark (zstd -b3 -i2)...")
    st5 = run_stage(
        "Compression Benchmark (zstd -b3 -i2)",
        lambda: subprocess.run(
            ["./workloads/build_target/zstd/programs/zstd", "-b3", "-i2", "./workloads/build_target/zstd/programs/zstd"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(REPO_ROOT),
            check=True,
        ),
        helper,
    )
    stages.append(st5)
    print(f"    -> Time: {st5['duration_s']}s | Energy: {st5['energy_j']} J | Power: {st5['power_w']} W")

    tot_time = sum(s["duration_s"] for s in stages)
    tot_energy = sum(s["energy_j"] for s in stages)
    avg_power = tot_energy / tot_time if tot_time > 0 else 0.0

    print(f"[{label}] Total Run Completed in {tot_time:.2f}s | {tot_energy:.1f} J | Avg {avg_power:.1f} W")

    return {
        "label": label,
        "total_duration_s": round(tot_time, 2),
        "total_energy_j": round(tot_energy, 1),
        "avg_power_w": round(avg_power, 2),
        "stages": stages,
    }


def main():
    print("=" * 72)
    print("    JOULECTRL AUTO-PILOT vs DEFAULT COMPARISON BENCHMARK")
    print("=" * 72)
    print("Workload: Compressed Multi-Stage Developer Workflow")
    print("  1. Parallel C++ Compile (zstd -j8)")
    print("  2. Think Time / Code Inspection (4.0s idle)")
    print("  3. Arithmetic Compute Kernel (16 workers, fixed compute)")
    print("  4. Review Pause (3.0s idle)")
    print("  5. Compression Benchmark (zstd -b3 -i2)")
    print("=" * 72)

    helper = HelperClient()

    # Step 1: Ensure system is completely stock and Auto-Pilot is disarmed
    print("\nEnsuring stock conditions and disarming Auto-Pilot...")
    try:
        api_post("/api/autopilot/disarm")
    except Exception as e:
        print("Note on disarm:", e)
    helper.restore()
    helper.end_session()

    # Verify Stock State
    try:
        boost_raw = Path("/sys/devices/system/cpu/cpufreq/boost").read_text().strip()
        print(f"Stock Boost verified: {boost_raw == '1'} (boost={boost_raw})")
    except Exception:
        pass

    # Settle
    print("Cooling down 5s before baseline run...")
    time.sleep(5.0)

    # -------------------------------------------------------------------------
    # RUN 1: DEFAULT STOCK
    # -------------------------------------------------------------------------
    print("\n" + "#" * 72)
    print("RUN 1: DEFAULT STOCK (Boost 5.09 GHz, Auto-Pilot OFF)")
    print("#" * 72)

    t_wall_start = time.perf_counter()
    e_wall_start = helper.read_energy()["uj"]

    stock_results = execute_developer_workload("Default (Stock)", helper)

    t_wall_end = time.perf_counter()
    e_wall_end = helper.read_energy()["uj"]

    stock_total_wall_s = t_wall_end - t_wall_start
    stock_total_rapl_j = delta_energy_j(e_wall_start, e_wall_end)

    # -------------------------------------------------------------------------
    # INTER-RUN COOL DOWN & ARM AUTOPILOT
    # -------------------------------------------------------------------------
    print("\n" + "-" * 72)
    print("Cooling down 6s before Auto-Pilot run to equalize initial thermals...")
    time.sleep(6.0)

    print("Arming Auto-Pilot Mode with target savings ~20%...")
    arm_res = api_post("/api/autopilot/arm", {
        "target_savings_pct": 20.0,
        "onset_s": 1.0,
        "idle_grace_s": 2.0,
        "poll_hz": 2.0,
    })
    print(f"Auto-Pilot Armed: {arm_res.get('ok')}")
    print(f"Matched Pareto Config: {arm_res.get('curve_config_id')}")
    print(f"Predicted Savings: {arm_res.get('empirical_savings_pct')}%, Predicted Penalty: {arm_res.get('empirical_runtime_penalty_pct')}%")
    time.sleep(1.0)

    # -------------------------------------------------------------------------
    # RUN 2: AUTO-PILOT MODE
    # -------------------------------------------------------------------------
    print("\n" + "#" * 72)
    print("RUN 2: AUTO-PILOT MODE (Target ~20% Energy Savings, Dynamic Clamping)")
    print("#" * 72)

    t_wall_start = time.perf_counter()
    e_wall_start = helper.read_energy()["uj"]

    auto_results = execute_developer_workload("Auto-Pilot", helper)

    t_wall_end = time.perf_counter()
    e_wall_end = helper.read_energy()["uj"]

    auto_total_wall_s = t_wall_end - t_wall_start
    auto_total_rapl_j = delta_energy_j(e_wall_start, e_wall_end)

    # Query final AutoPilot status & receipts
    st_auto = api_get("/api/autopilot/status")

    # Clean disarm
    api_post("/api/autopilot/disarm")
    helper.restore()
    helper.end_session()
    print("\nAuto-Pilot cleanly disarmed and system restored to stock.")

    # -------------------------------------------------------------------------
    # COMPARISON & METRICS
    # -------------------------------------------------------------------------
    energy_saved_j = stock_total_rapl_j - auto_total_rapl_j
    savings_pct = (energy_saved_j / stock_total_rapl_j) * 100.0 if stock_total_rapl_j > 0 else 0.0

    runtime_delta_s = auto_total_wall_s - stock_total_wall_s
    runtime_stretch_pct = (runtime_delta_s / stock_total_wall_s) * 100.0 if stock_total_wall_s > 0 else 0.0

    stock_avg_w = stock_total_rapl_j / stock_total_wall_s if stock_total_wall_s > 0 else 0.0
    auto_avg_w = auto_total_rapl_j / auto_total_wall_s if auto_total_wall_s > 0 else 0.0
    power_reduction_pct = ((stock_avg_w - auto_avg_w) / stock_avg_w) * 100.0 if stock_avg_w > 0 else 0.0

    # Energy-Delay Product (EDP = E * T)
    stock_edp = (stock_total_rapl_j * stock_total_wall_s) / 1000.0
    auto_edp = (auto_total_rapl_j * auto_total_wall_s) / 1000.0
    edp_change_pct = ((auto_edp - stock_edp) / stock_edp) * 100.0

    # 60 Wh laptop battery extrapolation
    battery_wh = 60.0
    stock_hours = (battery_wh / stock_avg_w) if stock_avg_w > 0 else 0.0
    auto_hours = (battery_wh / auto_avg_w) if auto_avg_w > 0 else 0.0
    extra_battery_mins = (auto_hours - stock_hours) * 60.0

    print("\n" + "=" * 72)
    print("                 HEAD-TO-HEAD COMPARISON RESULTS")
    print("=" * 72)
    print(f"{'Metric':<34} | {'Default (Stock)':<16} | {'Auto-Pilot':<16} | {'Delta / Impact'}")
    print("-" * 72)
    print(f"{'Total RAPL Energy (Joules)':<34} | {stock_total_rapl_j:>14.1f} J | {auto_total_rapl_j:>14.1f} J | -{energy_saved_j:.1f} J (-{savings_pct:.1f}%)")
    print(f"{'Total Wall Time (Seconds)':<34} | {stock_total_wall_s:>14.2f} s | {auto_total_wall_s:>14.2f} s | +{runtime_delta_s:.2f} s (+{runtime_stretch_pct:.1f}%)")
    print(f"{'Average Package Power (Watts)':<34} | {stock_avg_w:>14.1f} W | {auto_avg_w:>14.1f} W | -{power_reduction_pct:.1f}%")
    print(f"{'Energy Delay Product (kJ·s)':<34} | {stock_edp:>14.2f}   | {auto_edp:>14.2f}   | {edp_change_pct:+.1f}%")
    print(f"{'60 Wh Battery Runtime Est.':<34} | {stock_hours:>14.2f} h | {auto_hours:>14.2f} h | +{extra_battery_mins:.1f} mins")
    print("=" * 72)

    print("\nSTAGE-BY-STAGE BREAKDOWN:")
    print("-" * 72)
    print(f"{'Stage Name':<32} | {'Default Time/J':<17} | {'Auto-Pilot Time/J':<17} | {'Energy Saved'}")
    print("-" * 72)
    for s_st, a_st in zip(stock_results["stages"], auto_results["stages"]):
        e_diff = s_st["energy_j"] - a_st["energy_j"]
        e_pct = (e_diff / s_st["energy_j"] * 100.0) if s_st["energy_j"] > 0 else 0.0
        stock_str = f"{s_st['duration_s']}s / {s_st['energy_j']}J"
        auto_str = f"{a_st['duration_s']}s / {a_st['energy_j']}J"
        diff_str = f"-{e_diff:.1f}J (-{e_pct:.1f}%)" if e_diff >= 0 else f"+{abs(e_diff):.1f}J (+{abs(e_pct):.1f}%)"
        print(f"{s_st['name']:<32} | {stock_str:<17} | {auto_str:<17} | {diff_str}")
    print("-" * 72)

    output_data = {
        "workload": "Developer Multi-Stage Active Workflow",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target_savings_pct": 20.0,
        "matched_config_id": arm_res.get("curve_config_id"),
        "empirical_predicted_savings_pct": arm_res.get("empirical_savings_pct"),
        "empirical_predicted_runtime_penalty_pct": arm_res.get("empirical_runtime_penalty_pct"),
        "stock": {
            "total_wall_s": round(stock_total_wall_s, 2),
            "total_energy_j": round(stock_total_rapl_j, 1),
            "avg_power_w": round(stock_avg_w, 2),
            "stages": stock_results["stages"],
        },
        "autopilot": {
            "total_wall_s": round(auto_total_wall_s, 2),
            "total_energy_j": round(auto_total_rapl_j, 1),
            "avg_power_w": round(auto_avg_w, 2),
            "stages": auto_results["stages"],
            "service_status": st_auto,
        },
        "comparison": {
            "energy_saved_j": round(energy_saved_j, 1),
            "savings_pct": round(savings_pct, 1),
            "runtime_delta_s": round(runtime_delta_s, 2),
            "runtime_stretch_pct": round(runtime_stretch_pct, 1),
            "power_reduction_pct": round(power_reduction_pct, 1),
            "stock_edp": round(stock_edp, 2),
            "auto_edp": round(auto_edp, 2),
            "battery_hours_stock": round(stock_hours, 2),
            "battery_hours_autopilot": round(auto_hours, 2),
            "extra_battery_mins": round(extra_battery_mins, 1),
        },
    }

    out_file = REPO_ROOT / "benchmark_comparison_result.json"
    out_file.write_text(json.dumps(output_data, indent=2))
    print(f"\nDetailed benchmark result saved to: {out_file}")


if __name__ == "__main__":
    main()
