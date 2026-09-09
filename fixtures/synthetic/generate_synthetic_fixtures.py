"""fixtures/synthetic/generate_synthetic_fixtures.py — Generate auditable synthetic JSON fixtures."""

from __future__ import annotations

import json
from pathlib import Path

from core.models import (
    CalibrationRecord,
    ConfigSummary,
    Configuration,
    Profile,
    RunRecord,
    Selection,
    ValidationPair,
)

FIXTURES_DIR = Path(__file__).resolve().parent

def generate_all() -> None:
    exp_id = "exp_synthetic_clean_build_001"
    baseline_id = "cfg_stock_all"
    
    # 1. Configurations spec
    configs_spec = [
        {"id": "cfg_zen5_4c_stock", "layout": "A", "workers": 4, "cpus": [0, 2, 4, 6], "boost": True, "cap_khz": None, "t": 35.2, "e": 1420.0},
        {"id": "cfg_zen5_4c_4000", "layout": "A", "workers": 4, "cpus": [0, 2, 4, 6], "boost": False, "cap_khz": 4000000, "t": 38.4, "e": 1180.0},
        {"id": "cfg_zen5_4c_3000", "layout": "A", "workers": 4, "cpus": [0, 2, 4, 6], "boost": False, "cap_khz": 3000000, "t": 46.1, "e": 980.0},
        
        {"id": "cfg_zen5_8t_stock", "layout": "B", "workers": 8, "cpus": [0, 2, 4, 6, 8, 10, 12, 14], "boost": True, "cap_khz": None, "t": 31.8, "e": 1490.0},
        {"id": "cfg_zen5_8t_4000", "layout": "B", "workers": 8, "cpus": [0, 2, 4, 6, 8, 10, 12, 14], "boost": False, "cap_khz": 4000000, "t": 34.5, "e": 1210.0},
        {"id": "cfg_zen5_8t_3000", "layout": "B", "workers": 8, "cpus": [0, 2, 4, 6, 8, 10, 12, 14], "boost": False, "cap_khz": 3000000, "t": 42.0, "e": 1010.0},
        
        {"id": "cfg_zen5c_4c_stock", "layout": "C", "workers": 4, "cpus": [1, 3, 5, 7], "boost": True, "cap_khz": None, "t": 41.5, "e": 1050.0},
        {"id": "cfg_zen5c_4c_3000", "layout": "C", "workers": 4, "cpus": [1, 3, 5, 7], "boost": False, "cap_khz": 3000000, "t": 44.3, "e": 875.2},
        {"id": "cfg_zen5c_4c_2500", "layout": "C", "workers": 4, "cpus": [1, 3, 5, 7], "boost": False, "cap_khz": 2500000, "t": 51.2, "e": 820.0},
        {"id": "cfg_zen5c_4c_2000", "layout": "C", "workers": 4, "cpus": [1, 3, 5, 7], "boost": False, "cap_khz": 2000000, "t": 62.8, "e": 810.0},
        
        {"id": "cfg_stock_all", "layout": "D", "workers": 16, "cpus": list(range(16)), "boost": True, "cap_khz": None, "t": 28.5, "e": 1580.0},
        {"id": "cfg_all_16c_3000", "layout": "D", "workers": 16, "cpus": list(range(16)), "boost": False, "cap_khz": 3000000, "t": 35.8, "e": 1150.0},
    ]

    all_runs: list[RunRecord] = []
    config_summaries: dict[str, ConfigSummary] = {}

    for c in configs_spec:
        cid = c["id"]
        cfg = Configuration(
            id=cid,
            layout=c["layout"],
            worker_count=c["workers"],
            cpu_affinity=c["cpus"],
            freq_cap_khz=c["cap_khz"],
            boost=c["boost"],
        )
        t_base, e_base = c["t"], c["e"]
        runtimes = [round(t_base - 0.3, 2), round(t_base, 2), round(t_base + 0.4, 2)]
        energies = [round(e_base - 8.0, 1), round(e_base, 1), round(e_base + 11.0, 1)]

        for rep in range(1, 4):
            run = RunRecord(
                run_id=f"{cid}_r{rep}",
                experiment_id=exp_id,
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
                configuration=cfg,
            )
            all_runs.append(run)

        summary = ConfigSummary(
            config_id=cid,
            configuration=cfg,
            runtime_samples=runtimes,
            energy_samples=energies,
            median_runtime_s=runtimes[1],
            min_runtime_s=runtimes[0],
            max_runtime_s=runtimes[2],
            guarded_runtime_s=round(runtimes[2] * 1.05, 2),
            median_energy_j=energies[1],
            min_energy_j=energies[0],
            max_energy_j=energies[2],
            median_power_w=round(energies[1] / runtimes[1], 2),
            profile_is_usable=True,
            total_runs=3,
            is_baseline=(cid == baseline_id),
        )
        config_summaries[cid] = summary

    # Profile
    profile = Profile(
        experiment_id=exp_id,
        workload_name="clean_build",
        baseline_config_id=baseline_id,
        configurations=config_summaries,
        runs=all_runs,
        machine_fingerprint="synthetic-ryzen-ai-7-350",
        validity_state="valid",
        margin=0.05,
        suggested_budget_s=48.0,
    )

    with open(FIXTURES_DIR / "synthetic_profile.json", "w", encoding="utf-8") as f:
        json.dump(profile.to_dict(), f, indent=2)

    # 2. Selection
    winning_id = "cfg_zen5c_4c_3000"
    winning_cfg = config_summaries[winning_id].configuration
    sel = Selection(
        experiment_id=exp_id,
        objective_mode="deadline",
        status="selected",
        status_message="Lowest-energy measured configuration meeting your 48.0s runtime rule.",
        selected_config_id=winning_id,
        selected_configuration=winning_cfg,
        selected_median_energy_j=875.2,
        selected_guarded_runtime_s=round(44.7 * 1.05, 2),
        selected_median_runtime_s=44.3,
        baseline_config_id=baseline_id,
        baseline_median_energy_j=1580.0,
        baseline_median_runtime_s=28.5,
        energy_reduction_pct=round(100 * (1 - 875.2 / 1580.0), 1),
        runtime_increase_pct=round(100 * (44.3 / 28.5 - 1), 1),
        deadline_s=48.0,
        margin=0.05,
        energy_target_pct=70.0,
        perf_floor_pct=60.0,
        preference_outcome_state="both_met",
        frontier_config_ids=["cfg_stock_all", "cfg_zen5_8t_stock", "cfg_zen5_4c_4000", "cfg_zen5c_4c_3000", "cfg_zen5c_4c_2000"],
    )

    with open(FIXTURES_DIR / "synthetic_selection.json", "w", encoding="utf-8") as f:
        json.dump(sel.to_dict(), f, indent=2)

    # 3. Validation Pairs (3 pairs)
    val_pairs = []
    base_cfg = config_summaries[baseline_id].configuration
    for idx in range(1, 4):
        t_b = round(28.5 + (idx - 2) * 0.4, 2)
        e_b = round(1580.0 + (idx - 2) * 12.0, 1)
        t_s = round(44.3 + (idx - 2) * 0.5, 2)
        e_s = round(875.2 + (idx - 2) * 7.0, 1)

        b_run = RunRecord(
            run_id=f"val_b_{idx}",
            experiment_id=exp_id,
            config_id=baseline_id,
            workload_name="clean_build",
            repetition=idx,
            phase="validation",
            runtime_s=t_b,
            package_energy_j=e_b,
            energy_available=True,
            status="success",
            exit_code=0,
            output_verified=True,
            configuration=base_cfg,
        )
        s_run = RunRecord(
            run_id=f"val_s_{idx}",
            experiment_id=exp_id,
            config_id=winning_id,
            workload_name="clean_build",
            repetition=idx,
            phase="validation",
            runtime_s=t_s,
            package_energy_j=e_s,
            energy_available=True,
            status="success",
            exit_code=0,
            output_verified=True,
            configuration=winning_cfg,
        )

        pair = ValidationPair(
            pair_index=idx,
            baseline_run=b_run,
            selected_run=s_run,
            met_budget=(t_s <= 48.0),
            both_succeeded=True,
            live=False,
        )
        val_pairs.append(pair.to_dict())

    with open(FIXTURES_DIR / "synthetic_validation_pairs.json", "w", encoding="utf-8") as f:
        json.dump(val_pairs, f, indent=2)

    # 4. Calibration Records
    calib_records = [
        # C1 stock single-core Zen 5 vs Zen 5c
        CalibrationRecord(
            calibration_id="calib_c1_zen5",
            core_class="fast",
            layout="C1",
            cpus=[0],
            requested_control={"boost": True, "cap_khz": None},
            accepted_control={"boost": True, "cap_khz": None, "cur_freq_khz": 5040000},
            runtime_s=1.29,
            package_energy_j=32.4,
            work_units=409600000,
            kernel_checksum="0x3a762069507139ac",
            machine_fingerprint="synthetic-ryzen-ai-7-350",
        ).to_dict(),
        CalibrationRecord(
            calibration_id="calib_c1_zen5c",
            core_class="efficient",
            layout="C1",
            cpus=[1],
            requested_control={"boost": True, "cap_khz": None},
            accepted_control={"boost": True, "cap_khz": None, "cur_freq_khz": 3480000},
            runtime_s=1.85,
            package_energy_j=24.1,
            work_units=409600000,
            kernel_checksum="0x3a762069507139ac",
            machine_fingerprint="synthetic-ryzen-ai-7-350",
        ).to_dict(),
        # C2 multi-core scaling stock
        CalibrationRecord(
            calibration_id="calib_c2_zen5_stock",
            core_class="fast",
            layout="C2",
            cpus=[0, 2, 4, 6],
            requested_control={"boost": True, "cap_khz": None},
            accepted_control={"boost": True, "cap_khz": None, "cur_freq_khz": 4900000},
            runtime_s=0.34,
            package_energy_j=34.2,
            work_units=409600000,
            scaling_efficiency=0.95,
            kernel_checksum="0x3a762069507139ac",
            machine_fingerprint="synthetic-ryzen-ai-7-350",
        ).to_dict(),
        CalibrationRecord(
            calibration_id="calib_c2_zen5c_stock",
            core_class="efficient",
            layout="C2",
            cpus=[1, 3, 5, 7],
            requested_control={"boost": True, "cap_khz": None},
            accepted_control={"boost": True, "cap_khz": None, "cur_freq_khz": 3400000},
            runtime_s=0.49,
            package_energy_j=25.8,
            work_units=409600000,
            scaling_efficiency=0.94,
            kernel_checksum="0x3a762069507139ac",
            machine_fingerprint="synthetic-ryzen-ai-7-350",
        ).to_dict(),
    ]

    with open(FIXTURES_DIR / "synthetic_calibration_records.json", "w", encoding="utf-8") as f:
        json.dump(calib_records, f, indent=2)

    print("Synthetic fixtures generated successfully.")

if __name__ == "__main__":
    generate_all()
