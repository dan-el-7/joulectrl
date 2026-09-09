"""api/fixtures.py — deterministic fixture data for Joulectrl Dashboard & API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from core.models import (
    CapabilityReport,
    ConfigSummary,
    Configuration,
    CoreClassMap,
    CpuCore,
    CpuTopology,
    Profile,
    RunRecord,
    Selection,
    ValidationPair,
    utc_now_iso,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "real"


def get_fixture_capabilities() -> dict[str, Any]:
    """Return capability report loaded from real fixture if present, or fallback."""
    cap_file = FIXTURES_DIR / "capability_report.json"
    if cap_file.exists():
        try:
            with open(cap_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            return {
                "machine": {
                    "hostname": raw.get("machine", "demo-laptop"),
                    "cpu_model": raw.get("cpu", {}).get("model", "AMD Ryzen AI 7 350 w/ Radeon 860M"),
                    "boot_id": raw.get("boot_id", "6a6eb70b-267a-4ede-a0b9-b15ce2cb6fc2"),
                    "os": "Linux 6.10 Fedora 44",
                    "tuned_active_profile": raw.get("pm_daemons", {}).get("tuned_profile", "throughput-performance"),
                    "ac_power": raw.get("ac_power", True),
                },
                "topology": {
                    "logical_cores": raw.get("cpu", {}).get("ncpu", 16),
                    "physical_cores": raw.get("cpu", {}).get("n_cores", 8),
                    "classes": {
                        "fast": raw.get("core_classes", {}).get("fast", {}).get("cpus", [0, 2, 4, 6, 8, 10, 12, 14]),
                        "efficient": raw.get("core_classes", {}).get("efficient", {}).get("cpus", [1, 3, 5, 7, 9, 11, 13, 15]),
                    },
                    "driver": raw.get("cpufreq", {}).get("driver", "amd-pstate-epp"),
                    "governor": raw.get("cpufreq", {}).get("governor", "performance"),
                    "cpufreq_policies_count": raw.get("cpufreq", {}).get("n_policies", 16),
                },
                "energy": {
                    "backend": raw.get("package_energy", {}).get("backend", "powercap sysfs"),
                    "domain": raw.get("package_energy", {}).get("domain", "package-0"),
                    "available": True,
                    "root_required": raw.get("package_energy", {}).get("readable") == "root_only",
                    "max_energy_uj": raw.get("package_energy", {}).get("max_energy_range_uj", 65532610987),
                    "idle_watts": round(raw.get("package_energy", {}).get("idle_delta_uj_per_s", 8636424) / 1e6, 2),
                    "unit": "joules",
                },
                "controls": {
                    "boost_toggle": True,
                    "frequency_caps": True,
                    "epp_control": False,
                    "effective_tier": raw.get("recommended_mode", "full"),
                },
                "restoration": {
                    "supported": True,
                    "snapshot_present": False,
                    "status": "restored",
                },
            }
        except Exception:
            pass

    # Standard fallback
    return {
        "machine": {
            "hostname": "demo-laptop",
            "cpu_model": "AMD Ryzen AI 7 350 w/ Radeon 860M",
            "boot_id": "6a6eb70b-267a-4ede-a0b9-b15ce2cb6fc2",
            "os": "Linux 6.10 Fedora 44",
            "tuned_active_profile": "throughput-performance",
            "ac_power": True,
        },
        "topology": {
            "logical_cores": 16,
            "physical_cores": 8,
            "classes": {
                "fast": [0, 2, 4, 6, 8, 10, 12, 14],
                "efficient": [1, 3, 5, 7, 9, 11, 13, 15],
            },
            "driver": "amd-pstate-epp",
            "governor": "performance",
            "cpufreq_policies_count": 16,
        },
        "energy": {
            "backend": "powercap sysfs",
            "domain": "package-0",
            "available": True,
            "root_required": True,
            "max_energy_uj": 65532610987,
            "idle_watts": 8.6,
            "unit": "joules",
        },
        "controls": {
            "boost_toggle": True,
            "frequency_caps": True,
            "epp_control": False,
            "effective_tier": "full",
        },
        "restoration": {
            "supported": True,
            "snapshot_present": False,
            "status": "restored",
        },
    }


def get_fixture_workloads() -> list[dict[str, Any]]:
    return [
        {
            "id": "clean_build",
            "name": "Repeatable Clean Compilation",
            "description": "Compiles the workload in an isolated build directory with fixed source tree.",
            "parameters": {
                "target": "default",
                "parallel_range": [1, 16],
            },
        },
        {
            "id": "fixed_compute",
            "name": "Fixed-work Compute Benchmark",
            "description": "Fixed chunk computation with deterministic checksum verification.",
            "parameters": {
                "chunks": 64,
                "work_per_chunk": 100000,
            },
        },
    ]


def build_fixture_experiment(experiment_id: str = "exp_demo_clean_build") -> dict[str, Any]:
    """Create a complete, realistic experiment matching the demo laptop facts."""
    # 12 configurations
    configs_spec = [
        # Layout A: Zen 5 physical cores (4 workers)
        {"id": "cfg_zen5_4c_stock", "layout": "A", "workers": 4, "cpus": [0, 2, 4, 6], "boost": True, "cap_khz": None, "t": 35.2, "e": 1420.0},
        {"id": "cfg_zen5_4c_4000", "layout": "A", "workers": 4, "cpus": [0, 2, 4, 6], "boost": False, "cap_khz": 4000000, "t": 38.4, "e": 1180.0},
        {"id": "cfg_zen5_4c_3000", "layout": "A", "workers": 4, "cpus": [0, 2, 4, 6], "boost": False, "cap_khz": 3000000, "t": 46.1, "e": 980.0},
        
        # Layout B: Zen 5 with SMT (8 workers)
        {"id": "cfg_zen5_8t_stock", "layout": "B", "workers": 8, "cpus": [0, 2, 4, 6, 8, 10, 12, 14], "boost": True, "cap_khz": None, "t": 31.8, "e": 1490.0},
        {"id": "cfg_zen5_8t_4000", "layout": "B", "workers": 8, "cpus": [0, 2, 4, 6, 8, 10, 12, 14], "boost": False, "cap_khz": 4000000, "t": 34.5, "e": 1210.0},
        {"id": "cfg_zen5_8t_3000", "layout": "B", "workers": 8, "cpus": [0, 2, 4, 6, 8, 10, 12, 14], "boost": False, "cap_khz": 3000000, "t": 42.0, "e": 1010.0},
        
        # Layout C: Zen 5c dense physical cores (4 workers)
        {"id": "cfg_zen5c_4c_stock", "layout": "C", "workers": 4, "cpus": [1, 3, 5, 7], "boost": True, "cap_khz": None, "t": 41.5, "e": 1050.0},
        {"id": "cfg_zen5c_4c_3000", "layout": "C", "workers": 4, "cpus": [1, 3, 5, 7], "boost": False, "cap_khz": 3000000, "t": 44.3, "e": 875.2}, # Winning config!
        {"id": "cfg_zen5c_4c_2500", "layout": "C", "workers": 4, "cpus": [1, 3, 5, 7], "boost": False, "cap_khz": 2500000, "t": 51.2, "e": 820.0},
        {"id": "cfg_zen5c_4c_2000", "layout": "C", "workers": 4, "cpus": [1, 3, 5, 7], "boost": False, "cap_khz": 2000000, "t": 62.8, "e": 810.0},
        
        # Layout D: All 16 logical CPUs
        {"id": "cfg_stock_all", "layout": "D", "workers": 16, "cpus": list(range(16)), "boost": True, "cap_khz": None, "t": 28.5, "e": 1580.0}, # Baseline config!
        {"id": "cfg_all_16c_3000", "layout": "D", "workers": 16, "cpus": list(range(16)), "boost": False, "cap_khz": 3000000, "t": 35.8, "e": 1150.0},
    ]

    all_runs: list[RunRecord] = []
    config_summaries: dict[str, ConfigSummary] = {}

    for cfg_data in configs_spec:
        cid = cfg_data["id"]
        cfg_obj = Configuration(
            id=cid,
            layout=cfg_data["layout"],
            worker_count=cfg_data["workers"],
            cpu_affinity=cfg_data["cpus"],
            freq_cap_khz=cfg_data["cap_khz"],
            boost=cfg_data["boost"],
        )
        t_base = cfg_data["t"]
        e_base = cfg_data["e"]

        # 3 repetitions
        runtimes = [round(t_base - 0.3, 2), round(t_base, 2), round(t_base + 0.4, 2)]
        energies = [round(e_base - 8.0, 1), round(e_base, 1), round(e_base + 11.0, 1)]

        for rep in range(1, 4):
            run = RunRecord(
                run_id=f"{cid}_r{rep}",
                experiment_id=experiment_id,
                config_id=cid,
                workload_name="clean_build",
                repetition=rep,
                mode="harness",
                phase="profiling",
                runtime_s=runtimes[rep - 1],
                package_energy_j=energies[rep - 1],
                energy_available=True,
                status="success",
                exit_code=0,
                output_verified=True,
                checksum="sha256_d41d8cd98f00b204e9800998ecf8427e",
                configuration=cfg_obj,
            )
            all_runs.append(run)

        # ConfigSummary
        is_base = (cid == "cfg_stock_all")
        guarded_t = round(max(runtimes) * 1.05, 2)
        summary = ConfigSummary(
            config_id=cid,
            configuration=cfg_obj,
            runtime_samples=runtimes,
            energy_samples=energies,
            median_runtime_s=runtimes[1],
            min_runtime_s=min(runtimes),
            max_runtime_s=max(runtimes),
            guarded_runtime_s=guarded_t,
            median_energy_j=energies[1],
            min_energy_j=min(energies),
            max_energy_j=max(energies),
            median_power_w=round(energies[1] / runtimes[1], 2),
            profile_is_usable=True,
            total_runs=3,
            is_baseline=is_base,
        )
        config_summaries[cid] = summary

    # Selection: deadline mode with budget 45.0s
    baseline_id = "cfg_stock_all"
    selected_id = "cfg_zen5c_4c_3000"
    base_sum = config_summaries[baseline_id]
    sel_sum = config_summaries[selected_id]

    savings_pct = round(100.0 * (1.0 - sel_sum.median_energy_j / base_sum.median_energy_j), 1)
    runtime_inc_pct = round(100.0 * (sel_sum.median_runtime_s / base_sum.median_runtime_s - 1.0), 1)

    selection_obj = Selection(
        experiment_id=experiment_id,
        objective_mode="deadline",
        status="selected",
        status_message="Lowest-energy measured configuration meeting the empirical runtime rule",
        selected_config_id=selected_id,
        selected_configuration=sel_sum.configuration,
        selected_median_energy_j=sel_sum.median_energy_j,
        selected_guarded_runtime_s=sel_sum.guarded_runtime_s,
        selected_median_runtime_s=sel_sum.median_runtime_s,
        baseline_config_id=baseline_id,
        baseline_median_energy_j=base_sum.median_energy_j,
        baseline_median_runtime_s=base_sum.median_runtime_s,
        energy_reduction_pct=savings_pct,
        runtime_increase_pct=runtime_inc_pct,
        deadline_s=45.0,
        margin=0.05,
        energy_target_pct=70.0,
        perf_floor_pct=60.0,
        preference_outcome_state="both_met",
        frontier_config_ids=[
            "cfg_stock_all",
            "cfg_zen5_8t_stock",
            "cfg_zen5_4c_stock",
            "cfg_zen5_4c_4000",
            "cfg_zen5_8t_3000",
            "cfg_zen5c_4c_3000",
            "cfg_zen5c_4c_2500",
            "cfg_zen5c_4c_2000",
        ],
    )

    # Validation pairs: 3 fresh executions comparing baseline vs selected
    val_pairs: list[ValidationPair] = []
    base_val_runs = [
        {"t": 28.6, "e": 1575.0},
        {"t": 28.4, "e": 1582.0},
        {"t": 28.7, "e": 1578.0},
    ]
    sel_val_runs = [
        {"t": 44.1, "e": 872.0},
        {"t": 44.5, "e": 879.0},
        {"t": 44.3, "e": 874.0},
    ]

    for i in range(3):
        r_base = RunRecord(
            run_id=f"val_base_r{i+1}",
            experiment_id=experiment_id,
            config_id=baseline_id,
            workload_name="clean_build",
            repetition=i + 1,
            mode="harness",
            phase="validation",
            runtime_s=base_val_runs[i]["t"],
            package_energy_j=base_val_runs[i]["e"],
            energy_available=True,
            status="success",
            exit_code=0,
            output_verified=True,
            configuration=base_sum.configuration,
        )
        r_sel = RunRecord(
            run_id=f"val_sel_r{i+1}",
            experiment_id=experiment_id,
            config_id=selected_id,
            workload_name="clean_build",
            repetition=i + 1,
            mode="harness",
            phase="validation",
            runtime_s=sel_val_runs[i]["t"],
            package_energy_j=sel_val_runs[i]["e"],
            energy_available=True,
            status="success",
            exit_code=0,
            output_verified=True,
            configuration=sel_sum.configuration,
        )
        pair = ValidationPair(
            pair_index=i + 1,
            baseline_run=r_base,
            selected_run=r_sel,
            met_budget=True,
        )
        val_pairs.append(pair)

    profile_obj = Profile(
        experiment_id=experiment_id,
        workload_name="clean_build",
        baseline_config_id=baseline_id,
        configurations=config_summaries,
        runs=all_runs,
        machine_fingerprint="6a6eb70b-267a-4ede-a0b9-b15ce2cb6fc2",
        validity_state="valid",
        margin=0.05,
        suggested_budget_s=45.0,
    )

    return {
        "id": experiment_id,
        "state": "COMPLETE",
        "created_at": "2026-09-09T10:00:00Z",
        "workload_id": "clean_build",
        "objective": "deadline",
        "runtime_budget_s": 45.0,
        "preference": {
            "energy_target_pct": 70.0,
            "perf_floor_pct": 60.0,
        },
        "profile": profile_obj.to_dict(),
        "selection": selection_obj.to_dict(),
        "validation": {
            "status": "verified",
            "pairs": [p.to_dict() for p in val_pairs],
            "verified_savings_pct": 44.6,
            "verified_runtime_delta_s": 15.7,
        },
        "restoration_status": "restored",
    }
