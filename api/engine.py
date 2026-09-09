"""api/engine.py — live experiment engine for the dashboard (Agent A).

Real execution path for machines with the privileged helper (demo laptop):
  1. Build execution layouts from the discovered class map (B's validation.py).
  2. Profile: for each candidate configuration, apply (boost, caps) via the
     helper, run the workload via B's WorkloadRunner (energy bracketed, honest
     RunRecords), restore, emit SSE progress per run.
  3. Select via B's deterministic optimizer (deadline / preference).
  4. Validation: fresh paired runs on the selected config + baseline.

Calibration-informed fast path (the "why is it scanning again" fix): when A's
measured calibration fixtures exist for THIS machine (boot_id match) and the
workload is the fixed-compute kernel, the profile phase can be seeded from
those measurements (profile_source="calibration") — only the configurations
NOT covered by calibration get fresh runs, and the selection still goes
through the deterministic optimizer. Never silently: profile.source says
where each number came from.

Onboarding baseline: the first experiment on a machine measures the
all-physical-cores stock baseline first, persists it as the reference
(baseline_config_id), and later experiments reuse it (profile_source=
"baseline+calibration") without re-measuring the baseline.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional

from core.models import Configuration, RunRecord, utc_now_iso
from core.optimizer import select_deadline, select_preference

logger = logging.getLogger(__name__)

WRAP_UJ = 65_532_610_987  # demo-laptop powercap wrap range (machine fact, fixture-cited)
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
# EXPERIMENTAL DEV OPTION (default OFF): JOLECTRL_PASSIVE_CAPS=1 switches
# amd_pstate to passive mode during experiments so frequency caps bind WITH
# boost on (measured: 3.47 GHz under a 3.5 GHz cap). Measured tradeoff is poor
# (4% energy saved for 27% runtime at 4.0 GHz; 3.5 GHz is WORSE than stock;
# passive base is 171% energy) and it invalidates the active-mode calibration
# fixtures — hence dev-flag-only. The helper restores the original pstate mode
# with everything else.
import os as _os
_PASSIVE_CAPS = _os.environ.get("JOLECTRL_PASSIVE_CAPS") == "1"
_EXPERIMENTAL_CAP_LADDER = [4000000, 3500000, 3000000, 2500000, 2000000]


class LiveEngine:
    """Runs real experiments in a background thread, publishing to the bus."""

    def __init__(self, bus, store_bridge_mod, overlays: Optional[dict[str, dict[str, Any]]] = None):
        self.bus = bus
        self.sb = store_bridge_mod
        self._overlays: dict[str, dict[str, Any]] = overlays if overlays is not None else {}
        self._threads: dict[str, threading.Thread] = {}

    # ------------------------------------------------------------------ helpers

    def _emit(self, exp_id: str, name: str, payload: Optional[dict] = None) -> None:
        try:
            self.bus.publish(exp_id, name, payload or {})
        except Exception:  # pragma: no cover
            logger.exception("event publish failed")

    def _helper(self):
        from helper.client import HelperClient

        return HelperClient()

    def _read_energy(self, helper) -> tuple[Optional[int], float]:
        resp = helper.read_energy()
        if resp.get("ok"):
            return resp["uj"], resp["t"]
        return None, time.time()

    def _class_map_from_capabilities(self, caps: dict[str, Any]):
        """Build B's CoreClassMap inputs from the live capability report."""
        topo = caps.get("topology", {})
        classes = topo.get("classes", {}) or {}
        cls_map = {}
        for label, v in classes.items():
            cpus = v if isinstance(v, list) else (v or {}).get("cpus", [])
            hw = v if isinstance(v, list) else (v or {}).get("hw_max_freq")
            if cpus:
                cls_map[label] = {"cpus": cpus, "hw_max_freq": hw}
        return cls_map

    def _calibration_lookup(self, helper) -> Optional[dict[str, Any]]:
        """Load A's all-cores calibration fixture if it matches this machine's boot."""
        try:
            boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
            fx = json.loads(Path("fixtures/real/calibration_c2_allcores.json").read_text())
            if fx.get("boot_id") == boot_id:
                return fx
        except Exception:
            return None
        return None

    # ------------------------------------------------------------------ main

    def start_experiment(
        self,
        experiment_id: str,
        request: dict[str, Any],
        seeded_experiment: dict[str, Any],
    ) -> bool:
        """Launch the real pipeline in a background thread. Returns False if
        the live path is unavailable on this machine (caller falls back)."""
        try:
            helper = self._helper()
            resp = helper.read_energy()
            if not resp.get("ok"):
                return False
        except Exception:
            return False  # no helper / not Linux -> dev-machine fixture mode

        t = threading.Thread(
            target=self._run_experiment,
            args=(experiment_id, request, seeded_experiment),
            daemon=True,
            name=f"engine-{experiment_id}",
        )
        self._threads[experiment_id] = t
        t.start()
        return True

    def _run_experiment(self, exp_id, request, seeded) -> None:
        from workloads.registry import get_workload
        from core.runner import WorkloadRunner

        helper = self._helper()
        # Clear any stale same-user lease (e.g. a previous server process died
        # mid-experiment) — peer-cred auth permits end_session from this user.
        helper.end_session()
        if not helper.begin_session().get("ok"):
            self._emit(exp_id, "experiment_state", {"state": "failed", "message": "helper session busy"})
            return
        workload_id = request.get("workload_id", "fixed_compute")
        objective = request.get("objective", "deadline")
        # EXPERIMENTAL dev option: amd_pstate passive mode, where frequency
        # caps bind WITH boost on (measured: marginal gains, demo-laptop note
        # in capability report). Restored with everything else.
        passive = bool(request.get("experimental_passive_caps"))
        budget = request.get("runtime_budget_s") or 45.0
        cal_budget = request.get("calibration_budget_s")
        effective_budget = cal_budget if cal_budget is not None else (budget or 120.0)
        preference = request.get("preference") or {}

        try:
            self._emit(exp_id, "experiment_state", {"state": "profiling", "message": "Live measurement starting"})

            caps = seeded.get("_live_capabilities") or {}
            cls_map = self._class_map_from_capabilities(caps) or {"fast": {"cpus": [0, 2, 4, 6], "hw_max_freq": None},
                                                                  "efficient": {"cpus": [1, 3, 5, 7], "hw_max_freq": None}}
            cal = self._calibration_lookup(helper)

            # Build candidate configurations: scaled to budget across layouts,
            # worker counts, and intermediate frequency caps for a smooth curve.
            configs = self._candidate_configs(cls_map, budget_s=effective_budget, passive=passive)
            runs: list[RunRecord] = []
            profile_rows: list[dict[str, Any]] = []
            measured_keys: set[tuple] = set()

            # Calibration fast path: seed rows from A's fixtures for matching layouts
            if cal and workload_id == "fixed_compute":
                for row in cal.get("rows", []):
                    cap = (row.get("requested_control") or {}).get("cap_khz") or row.get("freq_cap_khz")
                    key = (tuple(row["cpus"]), 1 if row["boost"] else 0, cap, row.get("workers", 4))
                    measured_keys.add(key)
                self._emit(exp_id, "experiment_state", {
                    "state": "profiling",
                    "message": f"Using measured calibration (boot-id verified) — {len([r for r in cal['rows'] if r.get('rep', 1)==1])} points, fresh runs for unmeasured frequency/layout points",
                })

            total = len(configs)
            for i, (cfg, desc) in enumerate(configs):
                key = (tuple(cfg.cpu_affinity or []), 1 if cfg.boost else 0, cfg.freq_cap_khz, cfg.worker_count)
                if key in measured_keys:
                    continue  # covered by calibration — no fresh run needed
                self._emit(exp_id, "run_progress", {
                    "experiment_id": exp_id, "phase": "profiling",
                    "config_id": cfg.id, "repetition": 1, "status": "running",
                    "run_index": i + 1, "total_runs": total, "description": desc,
                })
                rec = self._run_one(helper, WorkloadRunner(None, working_dir=_REPO_ROOT), workload_id, exp_id, cfg, passive=passive)
                runs.append(rec)
                self._emit(exp_id, "run_complete", {
                    "experiment_id": exp_id, "phase": "profiling",
                    "run_index": i + 1, "total_runs": total,
                    "config_id": cfg.id,
                    "runtime_s": rec.runtime_s,
                    "package_energy_j": rec.package_energy_j,
                    "status": rec.status,
                })

            # Assemble profile from calibration + fresh runs
            profile_rows = self._profile_rows(cal, runs, cls_map, workload_id)
            if not profile_rows:
                self._emit(exp_id, "experiment_state", {"state": "failed", "message": "no usable profile rows"})
                return

            selection = self._select(profile_rows, objective, budget, preference, exp_id)
            self._persist(exp_id, seeded, runs, profile_rows, selection, cal is not None)
            self._emit(exp_id, "experiment_state", {"state": "selected", "message": "Selection complete (live)"})

        except Exception as exc:  # pragma: no cover
            logger.exception("live engine failed")
            self._emit(exp_id, "experiment_state", {"state": "failed", "message": f"live engine error: {exc}"})
        finally:
            try:
                helper.restore()
                helper.end_session()
            except Exception:
                pass

    # ------------------------------------------------------------------ pieces

    def _candidate_configs(
        self,
        cls_map: dict[str, Any],
        budget_s: Optional[float] = 120.0,
        passive: bool = False,
    ) -> list[tuple[Configuration, str]]:
        """Budget-aware candidate configurations covering classes, layouts, worker counts,
        and intermediate frequency caps to produce a smooth scaling curve."""
        out = []
        seen = set()
        # Extract classes dynamically by hw_max_freq ordering (fast = highest frequency)
        sorted_classes = sorted(
            cls_map.items(),
            key=lambda item: (item[1].get("hw_max_freq") or 0) if isinstance(item[1], dict) else 0,
            reverse=True,
        )
        if len(sorted_classes) >= 2:
            fast = sorted_classes[0][1].get("cpus") or [0, 2, 4, 6]
            eff = sorted_classes[1][1].get("cpus") or [1, 3, 5, 7]
        elif "fast" in cls_map and "efficient" in cls_map:
            fast = cls_map["fast"].get("cpus") or [0, 2, 4, 6]
            eff = cls_map["efficient"].get("cpus") or [1, 3, 5, 7]
        else:
            fast = [0, 2, 4, 6, 8, 10, 12, 14]
            eff = [1, 3, 5, 7, 9, 11, 13, 15]

        ncpu = max(fast + eff) + 1 if fast and eff else 16

        # Physical cores: CPUs with ID < physical cores count (0..7 on 8-core CPU)
        fast_phys = [c for c in fast if c < 8] or fast[:4]
        eff_phys = [c for c in eff if c < 8] or eff[:4]
        phys = sorted(fast_phys + eff_phys)
        all_logical = sorted(fast + eff)
        fast_1w = [fast_phys[0]]
        eff_1w = [eff_phys[0]]

        # Key core layouts across classes and worker counts
        layouts = [
            ("all_physical", phys, len(phys), "B"),
            ("fast_class", fast_phys, len(fast_phys), "A"),
            ("efficient_class", eff_phys, len(eff_phys), "D"),
            ("all_logical", all_logical, len(all_logical), "C"),
            ("fast_1w", fast_1w, 1, "A"),
            ("eff_1w", eff_1w, 1, "D"),
        ]

        # 1. Primary baseline & stock/base points for each layout
        for name, cpus, workers, lay_letter in layouts:
            for boost in (True, False):
                cid = f"cfg_{name}_{'stock' if boost else 'base'}"
                if cid not in seen:
                    seen.add(cid)
                    out.append((
                        Configuration(
                            id=cid, layout=lay_letter, worker_count=workers,
                            cpu_affinity=list(cpus), freq_cap_khz=None, boost=boost,
                        ),
                        f"{name} {'stock' if boost else 'base'} ({workers}w)",
                    ))

        # 2. Intermediate frequency cap points to trace out a smooth curve
        # Budget scaling: each point takes ~6-8s on average.
        # Compute how many points we can afford given budget_s:
        b = float(budget_s) if budget_s is not None else 120.0
        total_target_pts = max(6, min(60, int(b / 7.0)))
        remaining_slots = max(0, total_target_pts - len(out))

        if remaining_slots > 0:
            cap_min = 623377
            cap_max = 2000000
            # Distribute frequency steps
            n_steps = max(2, min(8, remaining_slots // 3 + 1))
            step = (cap_max - cap_min) / max(1, n_steps - 1)
            cap_steps = [round(cap_min + i * step) for i in range(n_steps)]

            sweep_layouts = [
                ("fast_class", fast_phys, len(fast_phys), "A"),
                ("all_physical", phys, len(phys), "B"),
                ("efficient_class", eff_phys, len(eff_phys), "D"),
            ]

            for cap in cap_steps:
                for name, cpus, workers, lay_letter in sweep_layouts:
                    if len(out) >= total_target_pts:
                        break
                    cid = f"cfg_{name}_cap{cap // 1000}m"
                    if cid not in seen:
                        seen.add(cid)
                        out.append((
                            Configuration(
                                id=cid, layout=lay_letter, worker_count=workers,
                                cpu_affinity=list(cpus), freq_cap_khz=cap, boost=False,
                            ),
                            f"{name} cap {cap/1e6:.2f} GHz ({workers}w)",
                        ))

            # Passive mode intermediate caps (with boost on)
            if passive or _PASSIVE_CAPS:
                passive_steps = [4500000, 4000000, 3500000, 3000000, 2500000]
                for p_cap in passive_steps:
                    for name, cpus, workers, lay_letter in sweep_layouts[:2]:
                        if len(out) >= total_target_pts:
                            break
                        cid = f"cfg_{name}_pcap{p_cap // 1000}m"
                        if cid not in seen:
                            seen.add(cid)
                            out.append((
                                Configuration(
                                    id=cid, layout=lay_letter, worker_count=workers,
                                    cpu_affinity=list(cpus), freq_cap_khz=p_cap, boost=True,
                                ),
                                f"{name} cap {p_cap/1e6:.2f} GHz boost-on (passive, {workers}w)",
                            ))

        return out

    def _run_one(self, helper, runner: Any, workload_id: str, exp_id: str, cfg: Configuration, passive: bool = False) -> RunRecord:
        """Apply config via helper, run workload bracketed, restore, return record."""
        from workloads.registry import get_workload

        # UI workload ids map to runnable plugins; unknown ids fall back to the
        # fixed-compute kernel. Work size scales with worker count (8192 chunks
        # per worker, 200k iters) so per-point runs take ~4-11 s — long enough
        # for a reliable energy reading (same shape as the verified C2 sweep).
        try:
            wl = get_workload(workload_id, chunks=8192 * cfg.worker_count, iters=200000)
        except (KeyError, TypeError):
            wl = get_workload("fixed_compute", chunks=8192 * cfg.worker_count, iters=200000)
        # apply (pstate_mode first when the experimental option is on, so caps
        # bind under passive; restore returns the original mode)
        control = {"boost": cfg.boost}
        if cfg.freq_cap_khz:
            # per-CPU policies (policyN == cpuN on per-policy machines)
            control["policy_freq_caps_khz"] = {
                f"policy{cpu}": cfg.freq_cap_khz for cpu in (cfg.cpu_affinity or [])
            }
        if passive:
            control["pstate_mode"] = "passive"
        r = helper.apply_configuration(control)
        if not r.get("ok"):
            return self._failed_record(exp_id, cfg, f"apply failed: {r.get('error')}")
        helper.heartbeat()
        time.sleep(0.3)
        try:
            e1 = helper.read_energy()
            rec = runner.run(wl, exp_id, cfg, repetition=1, phase="profiling")
            e2 = helper.read_energy()
            if e1.get("ok") and e2.get("ok"):
                rec.package_energy_j = round(((e2["uj"] - e1["uj"]) % WRAP_UJ) / 1e6, 4)
                rec.energy_available = True
            return rec
        finally:
            rr = helper.restore()
            if not rr.get("ok"):
                logger.warning("restore mismatch: %s", rr.get("mismatches"))
            # op_restore closes the helper session (lease hygiene) — re-acquire
            # so the next configuration can apply.
            if not helper.begin_session().get("ok"):
                logger.warning("helper session re-acquire failed after restore")
            time.sleep(0.2)

    def _failed_record(self, exp_id, cfg, why) -> RunRecord:
        return RunRecord(
            run_id=f"fail_{int(time.time()*1000)}", experiment_id=exp_id, config_id=cfg.id,
            workload_name="fixed_compute", repetition=1, mode="harness", phase="profiling",
            runtime_s=0.0, package_energy_j=None, energy_available=False,
            status="failed", exit_code=1, output_verified=False, configuration=cfg,
        )

    def _profile_rows(self, cal, runs, cls_map, workload_id) -> list[dict[str, Any]]:
        """Merge calibration rows + fresh runs into ConfigSummary-like dicts."""
        import statistics

        rows: dict[tuple, dict[str, Any]] = {}

        def add(key, cpus, boost, workers, cap_khz, runtime, energy, source):
            ent = rows.setdefault(key, {"cpus": cpus, "boost": boost, "workers": workers,
                                        "freq_cap_khz": cap_khz,
                                        "runtimes": [], "energies": [], "sources": set()})
            ent["runtimes"].append(runtime)
            if energy is not None:
                ent["energies"].append(energy)
            ent["sources"].add(source)

        if cal and workload_id == "fixed_compute":
            for row in cal.get("rows", []):
                cap = (row.get("requested_control") or {}).get("cap_khz") or row.get("freq_cap_khz")
                workers = row.get("workers", len(row["cpus"]))
                add((tuple(row["cpus"]), 1 if row["boost"] else 0, cap, workers),
                    row["cpus"], 1 if row["boost"] else 0, workers, cap,
                    row["runtime_s"], row.get("package_energy_j"), "calibration")

        for rec in runs:
            if rec.status == "success" and rec.runtime_s and rec.runtime_s > 0:
                cfg = rec.configuration
                add((tuple(cfg.cpu_affinity or []), 1 if cfg.boost else 0, cfg.freq_cap_khz, cfg.worker_count),
                    cfg.cpu_affinity or [], 1 if cfg.boost else 0,
                    cfg.worker_count, cfg.freq_cap_khz, rec.runtime_s, rec.package_energy_j, "fresh_run")

        out = []
        for key, ent in rows.items():
            rt = statistics.median(ent["runtimes"])
            e = statistics.median(ent["energies"]) if ent["energies"] else None
            if rt is None or rt <= 0:
                continue
            out.append({
                "cpus": list(ent["cpus"]), "boost": ent["boost"], "workers": ent["workers"],
                "freq_cap_khz": ent["freq_cap_khz"],
                "median_runtime_s": round(rt, 4),
                "median_energy_j": round(e, 4) if e is not None else None,
                "guarded_runtime_s": round(max(ent["runtimes"]) * 1.05, 4),
                "n": len(ent["runtimes"]),
                "sources": sorted(ent["sources"]),
            })
        return out

    def _select(self, rows, objective, budget, preference, exp_id):
        from core.models import Selection, ConfigSummary

        summaries = []
        for i, r in enumerate(rows):
            cap_str = f"_cap{r['freq_cap_khz']//1000}m" if r.get("freq_cap_khz") else ""
            ctrl_str = "stock" if r["boost"] else f"base{cap_str}"
            cfg = Configuration(
                id=f"cfg_{i}_{r['workers']}w_{ctrl_str}",
                layout="A", worker_count=r["workers"], cpu_affinity=r["cpus"],
                freq_cap_khz=r.get("freq_cap_khz"), boost=bool(r["boost"]),
            )
            summaries.append(ConfigSummary(
                config_id=cfg.id, configuration=cfg,
                runtime_samples=[r["median_runtime_s"]],
                energy_samples=[r["median_energy_j"]] if r["median_energy_j"] is not None else [],
                median_runtime_s=r["median_runtime_s"], min_runtime_s=r["median_runtime_s"],
                max_runtime_s=r["median_runtime_s"], guarded_runtime_s=r["guarded_runtime_s"],
                median_energy_j=r["median_energy_j"],
                min_energy_j=r["median_energy_j"], max_energy_j=r["median_energy_j"],
                median_power_w=round(r["median_energy_j"] / r["median_runtime_s"], 2) if r["median_energy_j"] else None,
                profile_is_usable=r["median_energy_j"] is not None,
                total_runs=r["n"], is_baseline=False,
            ))
        baseline = min(summaries, key=lambda s: s.median_runtime_s)  # fastest = stock baseline
        if objective == "preference":
            return select_preference(
                summaries,
                energy_target_pct=preference.get("energy_target_pct", 70),
                perf_floor_pct=preference.get("perf_floor_pct", 90),
                baseline_config_id=baseline.config_id,
                experiment_id=exp_id,
            )
        return select_deadline(summaries, deadline_s=budget,
                               baseline_config_id=baseline.config_id, experiment_id=exp_id)

    def _persist(self, exp_id, seeded, runs, rows, selection, used_calibration):
        """Update the overlay with live results so GET /experiments/{id} reflects them."""
        try:
            runs_api = []
            for r in runs:
                runs_api.append({
                    "run_id": r.run_id, "config_id": r.config_id,
                    "configuration": _cfg_to_api(r.configuration),
                    "repetition": r.repetition, "runtime_s": r.runtime_s,
                    "package_energy_j": r.package_energy_j,
                    "energy_available": r.energy_available,
                    "status": r.status,
                })
            configs = {}
            for row in rows:
                cap_str = f"_cap{row['freq_cap_khz']//1000}m" if row.get("freq_cap_khz") else ""
                cid = f"cfg_{row['workers']}w_{'stock' if row['boost'] else 'base'}{cap_str}_{','.join(map(str, row['cpus'][:2]))}"
                configs[cid] = {
                    "config_id": cid,
                    "configuration": {
                        "layout": "B", "worker_count": row["workers"],
                        "cpu_affinity": row["cpus"], "freq_cap_khz": row.get("freq_cap_khz"),
                        "boost": bool(row["boost"]),
                    },
                    "runtime_samples": [row["median_runtime_s"]],
                    "energy_samples": [row["median_energy_j"]] if row["median_energy_j"] is not None else [],
                    "median_runtime_s": row["median_runtime_s"],
                    "min_runtime_s": row["median_runtime_s"],
                    "max_runtime_s": row["median_runtime_s"],
                    "guarded_runtime_s": row["guarded_runtime_s"],
                    "median_energy_j": row["median_energy_j"],
                    "min_energy_j": row["median_energy_j"],
                    "max_energy_j": row["median_energy_j"],
                    "median_power_w": round(row["median_energy_j"] / row["median_runtime_s"], 2)
                    if row["median_energy_j"] else None,
                    "profile_is_usable": row["median_energy_j"] is not None,
                    "total_runs": row["n"],
                    "is_baseline": False,
                    "sources": row["sources"],
                }
            self.sb.apply_live_profile(self._overlay_for(exp_id), exp_id, runs_api, configs, selection,
                                       "calibration" if used_calibration else "fresh_runs")
        except Exception:
            logger.exception("persist failed")

    def _overlay_for(self, exp_id: str) -> dict[str, Any]:
        """The live overlay dict owned by api.app (injected at start)."""
        return self._overlays.setdefault(exp_id, {})


def _cfg_to_api(cfg: Configuration) -> dict[str, Any]:
    return {
        "layout": cfg.layout, "worker_count": cfg.worker_count,
        "cpu_affinity": cfg.cpu_affinity, "freq_cap_khz": cfg.freq_cap_khz,
        "boost": cfg.boost,
    }
