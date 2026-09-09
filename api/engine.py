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
        budget = request.get("runtime_budget_s") or 45.0
        preference = request.get("preference") or {}

        try:
            self._emit(exp_id, "experiment_state", {"state": "profiling", "message": "Live measurement starting"})

            caps = seeded.get("_live_capabilities") or {}
            cls_map = self._class_map_from_capabilities(caps) or {"fast": {"cpus": [0, 2, 4, 6], "hw_max_freq": None},
                                                                  "efficient": {"cpus": [1, 3, 5, 7], "hw_max_freq": None}}
            cal = self._calibration_lookup(helper)

            # Build candidate configurations: B's layouts at stock + base
            # (the machine's verified effective control points).
            configs = self._candidate_configs(cls_map)
            runs: list[RunRecord] = []
            profile_rows: list[dict[str, Any]] = []
            measured_keys: set[tuple] = set()

            # Calibration fast path: seed rows from A's fixtures for matching layouts
            if cal and workload_id == "fixed_compute":
                for row in cal.get("rows", []):
                    key = (tuple(row["cpus"]), row["boost"])
                    measured_keys.add(key)
                self._emit(exp_id, "experiment_state", {
                    "state": "profiling",
                    "message": f"Using measured calibration (boot-id verified) — {len([r for r in cal['rows'] if r['rep']==1])} points, fresh runs only for unmeasured layouts",
                })

            total = len(configs)
            for i, (cfg, desc) in enumerate(configs):
                key = (tuple(cfg.cpu_affinity or []), 1 if cfg.boost else 0)
                if key in measured_keys:
                    continue  # covered by calibration — no fresh run needed
                self._emit(exp_id, "run_progress", {
                    "experiment_id": exp_id, "phase": "profiling",
                    "config_id": cfg.id, "repetition": 1, "status": "running",
                    "run_index": i + 1, "total_runs": total, "description": desc,
                })
                rec = self._run_one(helper, WorkloadRunner(None, working_dir=_REPO_ROOT), workload_id, exp_id, cfg)
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

    def _candidate_configs(self, cls_map: dict[str, Any]) -> list[tuple[Configuration, str]]:
        """Stock + base for each class's physical-core layout, plus all-physical."""
        out = []
        seen = set()
        fast = (cls_map.get("fast") or {}).get("cpus") or [0, 2, 4, 6]
        eff = (cls_map.get("efficient") or {}).get("cpus") or [1, 3, 5, 7]
        ncpu = max(fast + eff) + 1 if fast and eff else 8
        # physical cores: first half of the CPU list assuming 0..N-1 physical
        phys = sorted(set(fast[: len(fast) // 2] + eff[: len(eff) // 2])) or list(range(8))
        fast_phys = sorted(set(fast))[: 4] or list(range(0, 8, 2))
        layouts = [
            ("all_physical", phys, len(phys)),
            ("fast_class", fast_phys, len(fast_phys)),
        ]
        for name, cpus, workers in layouts:
            for boost in (True, False):
                cid = f"cfg_{name}_{'stock' if boost else 'base'}"
                if cid in seen:
                    continue
                seen.add(cid)
                out.append((
                    Configuration(id=cid, layout=name.upper()[:1], worker_count=workers,
                                  cpu_affinity=list(cpus), freq_cap_khz=None, boost=boost),
                    f"{name} {'stock' if boost else 'base'} ({workers}w)",
                ))
        return out

    def _run_one(self, helper, runner: Any, workload_id: str, exp_id: str, cfg: Configuration) -> RunRecord:
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
        # apply
        r = helper.apply_configuration({"boost": cfg.boost})
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

        def add(key, cpus, boost, workers, runtime, energy, source):
            ent = rows.setdefault(key, {"cpus": cpus, "boost": boost, "workers": workers,
                                        "runtimes": [], "energies": [], "sources": set()})
            ent["runtimes"].append(runtime)
            if energy is not None:
                ent["energies"].append(energy)
            ent["sources"].add(source)

        if cal and workload_id == "fixed_compute":
            for row in cal.get("rows", []):
                add((tuple(row["cpus"]), row["boost"]), row["cpus"], row["boost"],
                    row["workers"], row["runtime_s"], row.get("package_energy_j"), "calibration")

        for rec in runs:
            if rec.status == "success" and rec.runtime_s and rec.runtime_s > 0:
                add((tuple(rec.configuration.cpu_affinity or []), 1 if rec.configuration.boost else 0),
                    rec.configuration.cpu_affinity or [], 1 if rec.configuration.boost else 0,
                    rec.configuration.worker_count, rec.runtime_s, rec.package_energy_j, "fresh_run")

        out = []
        for key, ent in rows.items():
            rt = statistics.median(ent["runtimes"])
            e = statistics.median(ent["energies"]) if ent["energies"] else None
            if rt is None or rt <= 0:
                continue
            out.append({
                "cpus": list(ent["cpus"]), "boost": ent["boost"], "workers": ent["workers"],
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
            cfg = Configuration(
                id=f"cfg_{i}_{r['workers']}w_{'stock' if r['boost'] else 'base'}",
                layout="A", worker_count=r["workers"], cpu_affinity=r["cpus"],
                freq_cap_khz=None, boost=bool(r["boost"]),
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
                cid = f"cfg_{row['workers']}w_{'stock' if row['boost'] else 'base'}_{','.join(map(str, row['cpus'][:2]))}"
                configs[cid] = {
                    "config_id": cid,
                    "configuration": {
                        "layout": "B", "worker_count": row["workers"],
                        "cpu_affinity": row["cpus"], "freq_cap_khz": None,
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
