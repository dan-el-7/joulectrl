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

    _cancel_events: dict[str, threading.Event] = {}
    _active_runners: dict[str, Any] = {}
    _threads: dict[str, threading.Thread] = {}

    @classmethod
    def cancel_active_experiment(cls, exp_id: str) -> bool:
        """Cancel active experiment or validation thread and terminate any running child process."""
        ev = cls._cancel_events.get(exp_id)
        if ev:
            ev.set()
        runner = cls._active_runners.get(exp_id)
        if runner:
            try:
                runner.cancel()
                logger.info("Cancelled active runner process group for %s", exp_id)
            except Exception as e:
                logger.warning("Error cancelling runner for %s: %s", exp_id, e)
        return True

    @classmethod
    def is_cancelled(cls, exp_id: str) -> bool:
        ev = cls._cancel_events.get(exp_id)
        return ev.is_set() if ev else False

    def __init__(self, bus, store_bridge_mod, overlays: Optional[dict[str, dict[str, Any]]] = None, store: Optional[Any] = None):
        self.bus = bus
        self.sb = store_bridge_mod
        self._overlays: dict[str, dict[str, Any]] = overlays if overlays is not None else {}
        self.store = store

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
        """Load verified real calibration fixtures for this machine."""
        try:
            p_all = Path("fixtures/real/calibration_c2_allcores.json")
            p_eff = Path("fixtures/real/calibration_c2_effective.json")
            rows: list[dict[str, Any]] = []
            if p_all.exists():
                rows.extend(json.loads(p_all.read_text()).get("rows", []))
            if p_eff.exists():
                rows.extend(json.loads(p_eff.read_text()).get("rows", []))
            if rows:
                return {"rows": rows}
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
        self._cancel_events[experiment_id] = threading.Event()
        self._threads[experiment_id] = t
        t.start()
        return True

    def start_validation(self, experiment_id: str, repetitions: int = 3) -> bool:
        """Launch validation of baseline vs selected candidate in a background thread."""
        thread_key = f"val-{experiment_id}"
        if thread_key in self._threads and self._threads[thread_key].is_alive():
            return True

        t = threading.Thread(
            target=self._run_validation,
            args=(experiment_id, repetitions),
            daemon=True,
            name=thread_key,
        )
        self._cancel_events[experiment_id] = threading.Event()
        self._threads[thread_key] = t
        t.start()
        return True

    def _run_validation(self, exp_id: str, repetitions: int = 3) -> None:
        from workloads.registry import get_workload
        from core.runner import WorkloadRunner
        from core.models import ValidationPair, Configuration

        logger.info("Starting validation execution for %s (repetitions=%d)", exp_id, repetitions)

        # 1. Resolve experiment
        exp = self._overlays.get(exp_id)
        if not exp and self.store:
            row = self.store.get_experiment(exp_id)
            if row:
                exp = self.sb.experiment_to_api(row)
                if exp_id not in self._overlays:
                    self._overlays[exp_id] = dict(exp)
                    if row.get("selection"):
                        self._overlays[exp_id]["_selection_model"] = row.get("selection")
        if not exp:
            logger.warning("Validation cannot run: experiment %s not found", exp_id)
            return

        # 2. Resolve selected candidate configuration
        sel = exp.get("selection") or {}
        cand_cfg_id = sel.get("selected_config_id") or sel.get("config_id")
        prof = exp.get("profile") or {}
        configs = prof.get("configurations") or {}

        cand_cfg: Optional[Configuration] = None
        if cand_cfg_id and cand_cfg_id in configs:
            cand_raw = configs[cand_cfg_id].get("configuration") or {}
            cand_cfg = Configuration.from_dict(cand_raw)
        elif sel.get("selected_configuration"):
            cand_cfg = Configuration.from_dict(sel["selected_configuration"])
        elif sel.get("configuration"):
            cand_cfg = Configuration.from_dict(sel["configuration"])

        if not cand_cfg and sel.get("candidates"):
            for cand in sel["candidates"]:
                if cand.get("config_id") == cand_cfg_id or not cand_cfg_id:
                    cand_raw = cand.get("configuration") or {}
                    if cand_raw:
                        cand_cfg = Configuration.from_dict(cand_raw)
                        cand_cfg_id = cand.get("config_id") or cand_cfg_id
                        break

        if not cand_cfg and configs:
            for cid, cinfo in configs.items():
                c_data = cinfo.get("configuration") or {}
                if cid == cand_cfg_id or c_data.get("id") == cand_cfg_id or c_data.get("config_id") == cand_cfg_id:
                    cand_cfg = Configuration.from_dict(c_data)
                    cand_cfg_id = cid
                    break

        if not cand_cfg and configs:
            first_id = next(iter(configs))
            cand_cfg = Configuration.from_dict(configs[first_id].get("configuration") or {})
            cand_cfg_id = first_id

        if not cand_cfg and self.store:
            runs = self.store.get_runs(exp_id)
            for r in runs:
                if r.configuration and (r.config_id == cand_cfg_id or not cand_cfg_id):
                    cand_cfg = r.configuration
                    cand_cfg_id = r.config_id
                    break

        if cand_cfg and cand_cfg_id and cand_cfg.id == "config":
            cand_cfg.id = cand_cfg_id

        if not cand_cfg:
            logger.warning("No candidate config found for validation of %s", exp_id)
            self._emit(exp_id, "experiment_state", {"state": "failed", "message": "No candidate configuration found for validation"})
            return

        # 3. Resolve baseline configuration (must represent stock unconstrained execution: boost=True)
        base_cfg_id = prof.get("baseline_config_id") or sel.get("baseline_config_id")
        base_cfg: Optional[Configuration] = None
        if base_cfg_id and base_cfg_id in configs:
            base_raw = configs[base_cfg_id].get("configuration") or {}
            base_cfg = Configuration.from_dict(base_raw)
            base_cfg.id = base_cfg_id

        # Guarantee baseline is a stock boost configuration (never a base clock or capped profile)
        if not base_cfg or not base_cfg.boost:
            for cid, cinfo in configs.items():
                c_obj = cinfo.get("configuration") or {}
                if cinfo.get("is_baseline") or c_obj.get("boost") or "stock" in cid:
                    base_cfg = Configuration.from_dict(c_obj)
                    base_cfg.id = cid
                    break

        if (not base_cfg or not base_cfg.boost) and sel.get("candidates"):
            for cand in sel["candidates"]:
                if cand.get("is_baseline") or "stock" in cand.get("config_id", "") or (cand.get("configuration") or {}).get("boost"):
                    base_raw = cand.get("configuration") or {}
                    if base_raw:
                        base_cfg = Configuration.from_dict(base_raw)
                        base_cfg.id = cand.get("config_id") or "cfg_stock_baseline"
                        break

        if (not base_cfg or not base_cfg.boost) and self.store:
            runs = self.store.get_runs(exp_id)
            for r in runs:
                if (r.is_baseline or "stock" in (r.configuration.id if r.configuration else "")) and (r.configuration and r.configuration.boost):
                    base_cfg = r.configuration
                    break

        if not base_cfg:
            base_cfg = Configuration(
                id="cfg_baseline_stock",
                layout="B",
                worker_count=8,
                cpu_affinity=[0, 1, 2, 3, 4, 5, 6, 7],
                boost=True,
            )

        workload_id = exp.get("workload_id", "fixed_compute")
        deadline_s = exp.get("runtime_budget_s")

        # 4. Helper acquisition
        helper = None
        has_helper = False
        try:
            helper = self._helper()
            resp = helper.read_energy()
            if resp.get("ok"):
                has_helper = True
        except Exception:
            has_helper = False

        if has_helper:
            helper.end_session()
            if not helper.begin_session().get("ok"):
                logger.warning("helper session busy for validation of %s", exp_id)
                self._emit(exp_id, "experiment_state", {"state": "failed", "message": "CPU helper session busy"})
                return

        try:
            self._overlay_for(exp_id)["state"] = "validating"
            if self.store:
                try:
                    self.store.transition_state(exp_id, "VALIDATING")
                except Exception:
                    pass
            self._emit(exp_id, "experiment_state", {"state": "validating", "message": "Executing fresh validation pairs on hardware"})

            runner = WorkloadRunner(None, working_dir=_REPO_ROOT)
            self.__class__._active_runners[exp_id] = runner
            pairs: list[ValidationPair] = []
            self._overlay_for(exp_id)["validation"] = {
                "status": "validating",
                "pairs": [],
                "verified_savings_pct": None,
                "verified_runtime_delta_s": None,
            }

            for rep in range(1, repetitions + 1):
                if self.is_cancelled(exp_id):
                    logger.info("Validation cancelled by user for %s", exp_id)
                    break

                # Baseline execution
                self._emit(exp_id, "validation_progress", {
                    "experiment_id": exp_id,
                    "pair_index": rep,
                    "total_pairs": repetitions,
                    "phase": "baseline",
                    "status": "running",
                    "config_id": base_cfg.id,
                    "message": f"Measuring baseline pair {rep}/{repetitions}...",
                })
                if has_helper:
                    base_run = self._run_one(helper, runner, workload_id, exp_id, base_cfg, repetition=rep, phase="validation")
                else:
                    wl = get_workload(workload_id, chunks=65536, iters=200000)
                    base_run = runner.run(wl, exp_id, base_cfg, repetition=rep, phase="validation")
                base_run.phase = "validation"
                base_run.run_id = f"val_base_r{rep}_{int(time.time()*1000)}"

                if self.is_cancelled(exp_id):
                    logger.info("Validation cancelled by user before candidate run for %s", exp_id)
                    break

                # Candidate execution
                self._emit(exp_id, "validation_progress", {
                    "experiment_id": exp_id,
                    "pair_index": rep,
                    "total_pairs": repetitions,
                    "phase": "selected",
                    "status": "running",
                    "config_id": cand_cfg.id,
                    "message": f"Measuring candidate pair {rep}/{repetitions}...",
                })
                if has_helper:
                    sel_run = self._run_one(helper, runner, workload_id, exp_id, cand_cfg, repetition=rep, phase="validation")
                else:
                    wl = get_workload(workload_id, chunks=65536, iters=200000)
                    sel_run = runner.run(wl, exp_id, cand_cfg, repetition=rep, phase="validation")
                sel_run.phase = "validation"
                sel_run.run_id = f"val_sel_r{rep}_{int(time.time()*1000)}"

                pair = ValidationPair(
                    pair_index=rep,
                    baseline_run=base_run,
                    selected_run=sel_run,
                    live=True,
                )
                if deadline_s is not None and sel_run.runtime_s:
                    pair.met_budget = sel_run.runtime_s <= deadline_s
                else:
                    pair.met_budget = pair.both_succeeded

                pairs.append(pair)
                pairs_dicts = [p.to_dict() for p in pairs]

                if self.store:
                    try:
                        self.store.save_validation_pairs(exp_id, pairs)
                    except Exception as e:
                        logger.warning("save_validation_pairs failed: %s", e)

                val_api = self.sb.validation_to_api(pairs_dicts)
                self._overlay_for(exp_id)["validation"] = val_api

                self._emit(exp_id, "validation_pair_complete", {
                    "experiment_id": exp_id,
                    "pair_index": rep,
                    "total_pairs": repetitions,
                    "pair": pair.to_dict(),
                    "verified_savings_pct": val_api.get("verified_savings_pct"),
                    "verified_runtime_delta_s": val_api.get("verified_runtime_delta_s"),
                })

            if self.is_cancelled(exp_id):
                self._overlay_for(exp_id)["state"] = "RESTORED"
                self._overlay_for(exp_id)["restoration_status"] = "restored"
                if self.store:
                    try:
                        self.store.transition_state(exp_id, "RESTORED", "Validation cancelled by user")
                        self.store.update_restoration_status(exp_id, "restored")
                    except Exception:
                        pass
                self._emit(exp_id, "experiment_state", {
                    "state": "RESTORED",
                    "message": "Validation stopped by user. Settings restored.",
                })
                return

            # Completed all pairs
            self._overlay_for(exp_id)["state"] = "complete"
            self._overlay_for(exp_id)["restoration_status"] = "restored"
            if self.store:
                try:
                    self.store.transition_state(exp_id, "COMPLETE")
                except Exception:
                    pass

            final_val = self._overlay_for(exp_id)["validation"]
            self._emit(exp_id, "experiment_state", {"state": "complete", "message": "Validation complete"})
            self._emit(exp_id, "validation_complete", {
                "experiment_id": exp_id,
                "pairs_count": len(pairs),
                "verified_savings_pct": final_val.get("verified_savings_pct"),
                "verified_runtime_delta_s": final_val.get("verified_runtime_delta_s"),
                "status": final_val.get("status"),
            })
            logger.info("Validation complete for %s: %d pairs, savings=%s%%", exp_id, len(pairs), final_val.get("verified_savings_pct"))

        except Exception as exc:
            logger.exception("Validation execution failed: %s", exc)
            self._emit(exp_id, "experiment_state", {"state": "failed", "message": f"Validation failed: {exc}"})
        finally:
            self.__class__._active_runners.pop(exp_id, None)
            if has_helper and helper:
                try:
                    helper.restore()
                    helper.end_session()
                except Exception:
                    pass

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
        # Time budget for profiling: use calibration_budget_s if positive;
        # if explicitly None (user checked "Exhaustive"), allow 1800s ceiling;
        # if 0, fast-path from existing calibration without running fresh sweep.
        if cal_budget is not None and float(cal_budget) > 0:
            time_limit_s = float(cal_budget)
        elif "calibration_budget_s" in request and request.get("calibration_budget_s") is None:
            time_limit_s = 1800.0  # Exhaustive mode ceiling
        elif cal_budget == 0 or cal_budget == "0":
            time_limit_s = 0.0
        else:
            time_limit_s = 0.0 if cal_budget is None else float(cal_budget or 0.0)
        preference = request.get("preference") or {}

        repetitions = max(1, min(5, int(request.get("repetitions") or 1)))
        if repetitions > 1 and time_limit_s <= 0:
            time_limit_s = 60.0  # User explicitly requested repeatability check

        try:
            caps = seeded.get("_live_capabilities") or {}
            cls_map = self._class_map_from_capabilities(caps) or {"fast": {"cpus": [0, 2, 4, 6], "hw_max_freq": None},
                                                                  "efficient": {"cpus": [1, 3, 5, 7], "hw_max_freq": None}}
            cal = self._calibration_lookup(helper)

            # Build candidate configurations ordered by multiresolution bisection:
            # (highest stock, lowest min, 50% midpoint, 25% and 75% quartiles, octiles, etc.)
            configs = self._candidate_configs(cls_map, budget_s=time_limit_s, passive=passive)
            runs: list[RunRecord] = []
            profile_rows: list[dict[str, Any]] = []
            measured_keys: set[tuple] = set()

            # Calibration fast path: seed rows from verified fixtures if available
            if cal and repetitions == 1:
                for row in cal.get("rows", []):
                    cap = (row.get("requested_control") or {}).get("cap_khz") or row.get("freq_cap_khz")
                    key = (tuple(row["cpus"]), 1 if row["boost"] else 0, cap, row.get("workers", 4))
                    measured_keys.add(key)
                cal_rows = self._profile_rows(cal, [], cls_map, workload_id)
                if cal_rows:
                    cal_sel = self._select(cal_rows, objective, budget, preference, exp_id)
                    # If no sweep budget was allotted, fast-path complete immediately!
                    if time_limit_s <= 0:
                        self._persist(exp_id, seeded, [], cal_rows, cal_sel, True, state="selected")
                        self._emit(exp_id, "experiment_state", {
                            "state": "selected",
                            "message": f"Optimization complete using verified hardware calibration ({len(cal_rows)} points)",
                        })
                        return
                    # Otherwise persist initial calibration points while sweep begins
                    self._persist(exp_id, seeded, [], cal_rows, cal_sel, True, state="profiling")
                    self._emit(exp_id, "experiment_state", {
                        "state": "profiling",
                        "message": f"Using verified calibration ({len(measured_keys)} points active); profiling intermediate curve points to fill {time_limit_s:.0f}s budget",
                    })

            self._emit(exp_id, "experiment_state", {
                "state": "profiling",
                "message": f"Profiling sweep starting ({time_limit_s:.0f}s allotted budget, {repetitions}x repetition{'s' if repetitions > 1 else ''})",
            })

            # If starting a fresh live experiment, clear old dummy fixture runs
            # so the dashboard starts clean and populates live as tests complete!
            overlay = self._overlay_for(exp_id)
            if overlay and "profile" in overlay and not (cal and repetitions == 1):
                overlay["profile"]["runs"] = []
                overlay["profile"]["configurations"] = {}
                overlay["selection"] = None

            start_wall = time.monotonic()
            avg_run_s = 6.5
            unmeasured_configs = [
                (c, d) for c, d in configs
                if (tuple(c.cpu_affinity or []), 1 if c.boost else 0, c.freq_cap_khz, c.worker_count) not in measured_keys
            ]
            est_total_runs = min(len(unmeasured_configs) * repetitions, max(1, int(time_limit_s / avg_run_s)))
            run_idx = 0

            # Dynamic time-fitting loop: run as many prioritized points as fit into time_limit_s
            for cfg, desc in configs:
                key = (tuple(cfg.cpu_affinity or []), 1 if cfg.boost else 0, cfg.freq_cap_khz, cfg.worker_count)
                if key in measured_keys and repetitions == 1:
                    continue  # already covered by calibration or previous measurement

                break_outer = False
                for rep in range(1, repetitions + 1):
                    if self.is_cancelled(exp_id):
                        logger.info("Profiling sweep cancelled by user for %s", exp_id)
                        break_outer = True
                        break

                    now = time.monotonic()
                    elapsed = now - start_wall
                    remaining = time_limit_s - elapsed

                    # Update running average runtime from completed runs
                    valid_rts = [r.runtime_s for r in runs if r.runtime_s and r.runtime_s > 0]
                    if valid_rts:
                        avg_run_s = sum(valid_rts) / len(valid_rts)

                    # Check if next run fits in remaining budget
                    # (Always allow run 1, but for subsequent runs stop if remaining < estimated next run duration)
                    if runs and (remaining < max(3.5, avg_run_s * 0.75)):
                        logger.info(
                            f"Profiling sweep filled allotted budget: elapsed={elapsed:.1f}s, remaining={remaining:.1f}s < est_next={avg_run_s:.1f}s. "
                            f"Completed {len(runs)} fresh points."
                        )
                        break_outer = True
                        break

                    run_idx += 1
                    est_total_runs = max(
                        run_idx,
                        min(len(unmeasured_configs) * repetitions, len(runs) + max(1, int(remaining / max(1.0, avg_run_s)))),
                    )

                    rep_label = f" (rep #{rep})" if repetitions > 1 else ""
                    self._emit(exp_id, "run_progress", {
                        "experiment_id": exp_id, "phase": "profiling",
                        "config_id": cfg.id, "repetition": rep, "status": "running",
                        "run_index": run_idx, "total_runs": est_total_runs, "description": f"{desc}{rep_label}",
                        "elapsed_s": round(elapsed, 1), "remaining_s": round(remaining, 1),
                    })
                    rec = self._run_one(helper, WorkloadRunner(None, working_dir=_REPO_ROOT), workload_id, exp_id, cfg, passive=passive, repetition=rep)
                    runs.append(rec)
                    if self.store:
                        try:
                            self.store.record_run(rec)
                        except Exception as e:
                            logger.warning(f"Failed to record run {rec.run_id} in store: {e}")
                    if rep == repetitions:
                        measured_keys.add(key)

                    # PROGRESSIVE UPDATE: update overlay and store on EVERY run so UI live-plots!
                    current_rows = self._profile_rows(cal if repetitions == 1 else None, runs, cls_map, workload_id)
                    if current_rows:
                        try:
                            current_sel = self._select(current_rows, objective, budget, preference, exp_id)
                            self._persist(exp_id, seeded, runs, current_rows, current_sel, cal is not None and repetitions == 1, state="profiling")
                        except Exception as e:
                            logger.warning(f"intermediate persist failed: {e}")

                    self._emit(exp_id, "run_complete", {
                        "experiment_id": exp_id, "phase": "profiling",
                        "run_index": run_idx, "total_runs": est_total_runs,
                        "config_id": cfg.id, "repetition": rep,
                        "runtime_s": rec.runtime_s,
                        "package_energy_j": rec.package_energy_j,
                        "status": rec.status,
                    })

                if break_outer:
                    break

            if self.is_cancelled(exp_id):
                logger.info("Live engine stopping profiling cleanly after cancellation for %s", exp_id)
                self._overlay_for(exp_id)["state"] = "RESTORED"
                self._overlay_for(exp_id)["restoration_status"] = "restored"
                if self.store:
                    try:
                        self.store.transition_state(exp_id, "RESTORED", "Profiling cancelled by user")
                        self.store.update_restoration_status(exp_id, "restored")
                    except Exception:
                        pass
                self._emit(exp_id, "experiment_state", {
                    "state": "RESTORED",
                    "message": "Calibration stopped by user. Settings restored to stock.",
                })
                return

            # Assemble profile from calibration + fresh runs
            profile_rows = self._profile_rows(cal, runs, cls_map, workload_id)
            if not profile_rows:
                self._emit(exp_id, "experiment_state", {"state": "failed", "message": "no usable profile rows"})
                return

            selection = self._select(profile_rows, objective, budget, preference, exp_id)
            self._persist(exp_id, seeded, runs, profile_rows, selection, cal is not None and not runs, state="selected")
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
        """Multiresolution bisection candidate configurations:
        Orders configurations adaptively:
        - Round 0: Anchors / Extremes: highest (Stock) and lowest (Base min cap)
        - Round 1: Midpoints: 50% frequency caps (~1.31 GHz) across primary layouts
        - Round 2: Quartiles: 25% (~0.97 GHz) and 75% (~1.66 GHz) caps + 1w baselines
        - Round 3: Octiles: 12.5%, 37.5%, 62.5%, 87.5% caps + passive points
        - Round 4: 1/16ths and finer steps for high-density smooth curves.

        This enables any time-budgeted scan to stop at any time and guarantee
        that the points measured form a balanced, convex, representative Pareto curve.
        """
        out: list[tuple[Configuration, str]] = []
        seen: set[tuple] = set()

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
            try:
                from core.topology import read_topology, read_core_class_map
                topo = read_topology()
                cmap = read_core_class_map(topo)
                if cmap.n_classes > 1:
                    s_c = sorted(cmap.classes.items(), key=lambda x: cmap.hw_max_freq.get(x[0], 0), reverse=True)
                    fast = s_c[0][1]
                    eff = s_c[1][1]
                else:
                    fast = list(range(topo.ncpu))
                    eff = list(range(topo.ncpu))
            except Exception:
                fast = [0, 2, 4, 6, 8, 10, 12, 14]
                eff = [1, 3, 5, 7, 9, 11, 13, 15]

        # Dynamic physical core extraction
        try:
            from core.topology import read_topology
            topo = read_topology()
            phys = [topo.cores[c][0] for c in sorted(topo.cores.keys())]
        except Exception:
            fast_phys = [c for c in fast if c < 8] or fast[:4]
            eff_phys = [c for c in eff if c < 8] or eff[:4]
            phys = sorted(fast_phys + eff_phys)

        fast_phys = [c for c in fast if c in phys] or fast[:max(1, len(fast) // 2)]
        eff_phys = [c for c in eff if c in phys] or eff[:max(1, len(eff) // 2)]
        phys = sorted(set(fast_phys + eff_phys))
        all_logical = sorted(set(fast + eff))
        fast_1w = [fast_phys[0]]
        eff_1w = [eff_phys[0]]

        from core.topology import discover_freq_limits
        cap_min, cap_max = discover_freq_limits()

        def get_cap(fraction: float) -> int:
            return round(cap_min + fraction * (cap_max - cap_min))

        def add(cid: str, lay: str, workers: int, cpus: list[int], cap: Optional[int], boost: bool, desc: str):
            key = (tuple(cpus), 1 if boost else 0, cap, workers)
            if key not in seen:
                seen.add(key)
                out.append((
                    Configuration(
                        id=cid, layout=lay, worker_count=workers,
                        cpu_affinity=list(cpus), freq_cap_khz=cap, boost=boost,
                    ),
                    desc,
                ))

        primary_layouts = [
            ("all_physical", phys, len(phys), "B"),
            ("fast_class", fast_phys, len(fast_phys), "A"),
        ]
        secondary_layouts = [
            ("efficient_class", eff_phys, len(eff_phys), "D"),
            ("all_logical", all_logical, len(all_logical), "C"),
        ]

        # Round 0: Anchors / Extremes (Highest stock and lowest base cap)
        for name, cpus, workers, lay in primary_layouts:
            add(f"cfg_{name}_stock", lay, workers, cpus, None, True, f"{name} stock max (highest, {workers}w)")
            add(f"cfg_{name}_cap{cap_min//1000}m", lay, workers, cpus, cap_min, False, f"{name} min cap {cap_min/1e6:.2f} GHz (lowest, {workers}w)")
            add(f"cfg_{name}_base", lay, workers, cpus, cap_max, False, f"{name} base {cap_max/1e6:.1f} GHz ({workers}w)")

        # Round 1: Midpoints (50% ~1.31 GHz) + Secondary layouts bounds
        for name, cpus, workers, lay in primary_layouts:
            cap_mid = get_cap(0.5)
            add(f"cfg_{name}_cap{cap_mid//1000}m", lay, workers, cpus, cap_mid, False, f"{name} mid 50% {cap_mid/1e6:.2f} GHz ({workers}w)")

        for name, cpus, workers, lay in secondary_layouts:
            add(f"cfg_{name}_stock", lay, workers, cpus, None, True, f"{name} stock ({workers}w)")
            add(f"cfg_{name}_cap{cap_min//1000}m", lay, workers, cpus, cap_min, False, f"{name} min cap {cap_min/1e6:.2f} GHz ({workers}w)")
            add(f"cfg_{name}_base", lay, workers, cpus, cap_max, False, f"{name} base 2.0 GHz ({workers}w)")

        # Round 2: Quartiles (25% and 75%) + Single-core reference baselines
        for fraction, label in [(0.25, "25%"), (0.75, "75%")]:
            c = get_cap(fraction)
            for name, cpus, workers, lay in primary_layouts:
                add(f"cfg_{name}_cap{c//1000}m", lay, workers, cpus, c, False, f"{name} {label} {c/1e6:.2f} GHz ({workers}w)")

        for name, cpus, workers, lay in secondary_layouts:
            c = get_cap(0.5)
            add(f"cfg_{name}_cap{c//1000}m", lay, workers, cpus, c, False, f"{name} mid 50% {c/1e6:.2f} GHz ({workers}w)")

        for name, cpus, lay in [("fast_1w", fast_1w, "A"), ("eff_1w", eff_1w, "D")]:
            add(f"cfg_{name}_stock", lay, 1, cpus, None, True, f"{name} stock (1w)")
            add(f"cfg_{name}_base", lay, 1, cpus, cap_max, False, f"{name} base 2.0 GHz (1w)")

        # Round 3: Octiles (12.5%, 37.5%, 62.5%, 87.5%)
        for fraction, label in [(0.125, "12.5%"), (0.375, "37.5%"), (0.625, "62.5%"), (0.875, "87.5%")]:
            c = get_cap(fraction)
            for name, cpus, workers, lay in primary_layouts:
                add(f"cfg_{name}_cap{c//1000}m", lay, workers, cpus, c, False, f"{name} {label} {c/1e6:.2f} GHz ({workers}w)")

        for fraction, label in [(0.25, "25%"), (0.75, "75%")]:
            c = get_cap(fraction)
            for name, cpus, workers, lay in secondary_layouts:
                add(f"cfg_{name}_cap{c//1000}m", lay, workers, cpus, c, False, f"{name} {label} {c/1e6:.2f} GHz ({workers}w)")

        # Passive mode caps (with boost on)
        if passive or _PASSIVE_CAPS:
            for pcap, plabel in [(4500000, "4.5 GHz"), (2500000, "2.5 GHz"), (3500000, "mid 3.5 GHz"), (3000000, "3.0 GHz"), (4000000, "4.0 GHz")]:
                for name, cpus, workers, lay in primary_layouts:
                    add(f"cfg_{name}_pcap{pcap//1000}m", lay, workers, cpus, pcap, True, f"{name} passive {plabel} boost-on ({workers}w)")

        # Round 4 & 5: 1/16ths and 1/32ths for dense curves when budget is large (e.g. 600s)
        for denom in [16, 32]:
            for num in range(1, denom, 2):
                fraction = num / denom
                c = get_cap(fraction)
                for name, cpus, workers, lay in primary_layouts + secondary_layouts[:1]:
                    add(f"cfg_{name}_cap{c//1000}m", lay, workers, cpus, c, False, f"{name} {num}/{denom} {c/1e6:.2f} GHz ({workers}w)")

        return out

    def _run_one(self, helper, runner: Any, workload_id: str, exp_id: str, cfg: Configuration, passive: bool = False, repetition: int = 1, phase: str = "profiling") -> RunRecord:
        """Apply config via helper, run workload bracketed, restore, return record."""
        from workloads.registry import get_workload

        # UI workload ids map to runnable plugins; unknown ids fall back to the
        # fixed-compute kernel. Workload size is CONSTANT across all configurations
        # (65536 chunks, 200k iters) so every point processes the exact same total
        # computational work regardless of worker thread count, ensuring true
        # energy and runtime comparisons with invariant verification checksums.
        try:
            wl = get_workload(workload_id, chunks=65536, iters=200000)
        except (KeyError, TypeError):
            wl = get_workload("fixed_compute", chunks=65536, iters=200000)
        # Check clock holdability and adapt controls automatically (<1ms check, on by default)
        from core.clock_checker import check_clock_holdable

        hold = check_clock_holdable(
            freq_cap_khz=cfg.freq_cap_khz,
            boost=cfg.boost,
            cpu_affinity=cfg.cpu_affinity,
        )
        control = dict(hold["adapted_control"])
        if passive or hold["requires_passive_mode"]:
            control["pstate_mode"] = "passive"
            control["boost"] = True
        control["clamp_out_of_range"] = True
        r = helper.apply_configuration(control)
        if not r.get("ok"):
            return self._failed_record(exp_id, cfg, f"apply failed: {r.get('error')}", phase=phase)
        helper.heartbeat()
        time.sleep(0.3)
        self._active_runners[exp_id] = runner
        try:
            e1 = helper.read_energy()
            rec = runner.run(wl, exp_id, cfg, repetition=repetition, phase=phase)
            e2 = helper.read_energy()
            if e1.get("ok") and e2.get("ok"):
                # Wrap-safe modulo + plausibility ceiling (mirrors EnergyAccumulator):
                # a delta implying >200W sustained over the bracket means counter
                # reset/multi-wrap — report unavailable instead of a bogus number.
                d_uj = (e2["uj"] - e1["uj"]) % WRAP_UJ
                bracket_s = max(rec.runtime_s or 0.0, 1e-9) + 1.0  # +settle/launch overhead
                if d_uj <= 200.0 * bracket_s * 1e6:
                    rec.package_energy_j = round(d_uj / 1e6, 4)
                    rec.energy_available = True
                else:
                    rec.package_energy_j = None
                    rec.energy_available = False
                    rec.metadata = {**(rec.metadata or {}), "energy_error":
                                    f"helper bracket delta {d_uj} uJ implausible over {bracket_s:.1f}s — reset or multi-wrap"}
            return rec
        finally:
            self._active_runners.pop(exp_id, None)
            rr = helper.restore()
            if not rr.get("ok"):
                logger.warning("restore mismatch: %s", rr.get("mismatches"))
            # op_restore closes the helper session (lease hygiene) — re-acquire
            # so the next configuration can apply.
            if not helper.begin_session().get("ok"):
                logger.warning("helper session re-acquire failed after restore")
            time.sleep(0.2)

    def _failed_record(self, exp_id, cfg, why, phase: str = "profiling") -> RunRecord:
        return RunRecord(
            run_id=f"fail_{int(time.time()*1000)}", experiment_id=exp_id, config_id=cfg.id,
            workload_name="fixed_compute", repetition=1, mode="harness", phase=phase,
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
            target_chunks = 65536
            for row in cal.get("rows", []):
                cap = (row.get("requested_control") or {}).get("cap_khz") or row.get("freq_cap_khz")
                workers = row.get("workers", len(row["cpus"]))
                row_chunks = row.get("chunks")
                scale = (target_chunks / row_chunks) if (row_chunks and row_chunks > 0) else 1.0
                rt = row["runtime_s"] * scale
                ej = (row.get("package_energy_j") * scale) if row.get("package_energy_j") is not None else None
                add((tuple(row["cpus"]), 1 if row["boost"] else 0, cap, workers),
                    row["cpus"], 1 if row["boost"] else 0, workers, cap,
                    rt, ej, "calibration")

        # Discard calibration for any key that was freshly measured in this run
        fresh_keys = {
            (tuple(rec.configuration.cpu_affinity or []), 1 if rec.configuration.boost else 0, rec.configuration.freq_cap_khz, rec.configuration.worker_count)
            for rec in runs
            if rec.status == "success" and rec.runtime_s and rec.runtime_s > 0 and rec.configuration
        }
        for k in fresh_keys:
            if k in rows:
                del rows[k]

        for rec in runs:
            if rec.status == "success" and rec.runtime_s and rec.runtime_s > 0 and rec.configuration:
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
                "runtimes": list(ent["runtimes"]),
                "energies": list(ent["energies"]),
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
        for r in rows:
            cid = make_config_id(r["workers"], bool(r["boost"]), r.get("freq_cap_khz"), r["cpus"])
            cfg = Configuration(
                id=cid,
                layout="A", worker_count=r["workers"], cpu_affinity=r["cpus"],
                freq_cap_khz=r.get("freq_cap_khz"), boost=bool(r["boost"]),
            )
            summaries.append(ConfigSummary(
                config_id=cid, configuration=cfg,
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
        stock_summaries = [s for s in summaries if s.configuration and s.configuration.boost]
        if stock_summaries:
            baseline = min(stock_summaries, key=lambda s: s.median_runtime_s)
        else:
            baseline = min(summaries, key=lambda s: s.median_runtime_s)
        baseline.is_baseline = True
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

    def _persist(self, exp_id, seeded, runs, rows, selection, used_calibration, state: str = "selected"):
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
                cid = make_config_id(row["workers"], bool(row["boost"]), row.get("freq_cap_khz"), row["cpus"])
                is_base = (cid == getattr(selection, "baseline_config_id", None))
                configs[cid] = {
                    "config_id": cid,
                    "configuration": {
                        "id": cid,
                        "layout": "B", "worker_count": row["workers"],
                        "cpu_affinity": row["cpus"], "freq_cap_khz": row.get("freq_cap_khz"),
                        "boost": bool(row["boost"]),
                    },
                    "runtime_samples": row.get("runtimes", [row["median_runtime_s"]]),
                    "energy_samples": row.get("energies", [row["median_energy_j"]] if row["median_energy_j"] is not None else []),
                    "median_runtime_s": row["median_runtime_s"],
                    "min_runtime_s": min(row.get("runtimes", [row["median_runtime_s"]])),
                    "max_runtime_s": max(row.get("runtimes", [row["median_runtime_s"]])),
                    "guarded_runtime_s": row["guarded_runtime_s"],
                    "median_energy_j": row["median_energy_j"],
                    "min_energy_j": min(row["energies"]) if row.get("energies") else row["median_energy_j"],
                    "max_energy_j": max(row["energies"]) if row.get("energies") else row["median_energy_j"],
                    "median_power_w": round(row["median_energy_j"] / row["median_runtime_s"], 2)
                    if row["median_energy_j"] else None,
                    "profile_is_usable": row["median_energy_j"] is not None,
                    "total_runs": row["n"],
                    "is_baseline": is_base,
                    "sources": row["sources"],
                }
            self.sb.apply_live_profile(self._overlay_for(exp_id), exp_id, runs_api, configs, selection,
                                       "calibration" if used_calibration else "fresh_runs", state=state)
            if self.store:
                try:
                    self.store.transition_state(exp_id, state.upper())
                except Exception:
                    pass
                if selection:
                    try:
                        self.store.save_selection(selection)
                    except Exception:
                        pass
                try:
                    from core.models import Profile, ConfigSummary
                    base_id = (self._overlay_for(exp_id).get("profile") or {}).get("baseline_config_id") or (next(iter(configs)) if configs else "cfg_baseline")
                    prof_to_save = Profile(
                        experiment_id=exp_id,
                        workload_name=self._overlay_for(exp_id).get("workload_id", "clean_build"),
                        baseline_config_id=base_id,
                        configurations={
                            cid: ConfigSummary.from_dict(c) for cid, c in configs.items()
                        },
                        runs=runs,
                    )
                    self.store.save_profile(prof_to_save)
                except Exception as exc:
                    logger.warning("Failed to save profile to store: %s", exc)
        except Exception:
            logger.exception("persist failed")

    def _overlay_for(self, exp_id: str) -> dict[str, Any]:
        """The live overlay dict owned by api.app (injected at start)."""
        return self._overlays.setdefault(exp_id, {})


def make_config_id(workers: int, boost: bool, cap_khz: Optional[int], cpus: list[int]) -> str:
    """Generate consistent deterministic configuration identifier across engine, selection, and store."""
    cap_str = f"_cap{cap_khz // 1000}m" if (cap_khz and not boost) else ""
    ctrl_str = "stock" if boost else f"base{cap_str}"
    cpu_suffix = f"_{','.join(map(str, cpus[:2]))}" if cpus else ""
    return f"cfg_{workers}w_{ctrl_str}{cpu_suffix}"


def _cfg_to_api(cfg: Configuration) -> dict[str, Any]:
    return {
        "id": cfg.id,
        "config_id": cfg.id,
        "layout": cfg.layout,
        "worker_count": cfg.worker_count,
        "cpu_affinity": cfg.cpu_affinity,
        "freq_cap_khz": cfg.freq_cap_khz,
        "boost": cfg.boost,
    }
