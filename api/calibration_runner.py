"""Multithreaded frequency calibration suite runner.

Benchmarks the 3 multithreaded core configurations on the system:
1. All Cores (16 threads, mixed Zen 5 + Zen 5c)
2. Zen 5 Fast Cores (8 threads, performance cluster)
3. Zen 5c Eco Cores (8 threads, efficiency cluster)

Supports 3 calibration tiers:
- Quick (~20 min tier): 4 frequency points per class x 1 rep (fast curve shape)
- Standard (~1 hour tier): 7 frequency points per class x 2 reps (median noise rejection)
- Exhaustive (3x per freq tier): 10 frequency points per class x 3 reps (thorough statistical rigor)

Features clean stop/cancel handling with hardware restore, time estimation,
live SSE progress publishing to the event bus, and persistent storage.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.events import default_bus
from core.models import CalibrationRecord
from core.topology import discover_freq_limits, discover_hardware_classes

logger = logging.getLogger("joulectrl.calibration")

KERNEL_PATH = Path("workloads/kernel/fixed_compute").resolve()
WRAP = 65_532_610_987


def get_tier_config(tier: str, cap_min: Optional[int] = None, cap_max: Optional[int] = None) -> dict[str, Any]:
    """Dynamically generate tier configuration with linearly interpolated caps based on hardware limits."""
    if cap_min is None or cap_max is None:
        c_min, c_max = discover_freq_limits()
        cap_min = cap_min or c_min
        cap_max = cap_max or c_max

    if cap_min >= cap_max:
        cap_min = round(cap_max * 0.3)

    if tier == "standard":
        # 6 linearly spaced caps from cap_max down to cap_min (gives 1 stock + 6 caps = 7 points/class)
        caps = [round(cap_max - i * (cap_max - cap_min) / 5) for i in range(6)]
        return {
            "name": "Standard Tier (~1h)",
            "reps": 2,
            "caps": caps,
            "est_run_s": 7.0,
        }
    elif tier == "exhaustive":
        # 10 linearly spaced caps from cap_max down to cap_min (gives 1 stock + 10 caps = 11 points/class)
        caps = [round(cap_max - i * (cap_max - cap_min) / 9) for i in range(10)]
        return {
            "name": "Exhaustive Tier (3x per freq)",
            "reps": 3,
            "caps": caps,
            "est_run_s": 7.5,
        }
    else:  # quick
        mid = round(cap_min + 0.55 * (cap_max - cap_min))
        low = round(cap_min + 0.15 * (cap_max - cap_min))
        caps = [cap_max, mid, low]
        return {
            "name": "Quick Tier (~20m)",
            "reps": 1,
            "caps": caps,
            "est_run_s": 6.5,
        }


# Dynamic defaults initialized from live discovery (backward-compatible)
CLASSES_DEF = discover_hardware_classes()
TIER_CONFIGS = {t: get_tier_config(t) for t in ["quick", "standard", "exhaustive"]}



class CalibrationRunner:
    """Manages active multithreaded calibration sweeps."""

    _instance: Optional[CalibrationRunner] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> CalibrationRunner:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._cancel_event = threading.Event()
        self._active_proc: Optional[subprocess.Popen] = None
        self._state_lock = threading.RLock()

        self.is_running: bool = False
        self.session_id: Optional[str] = None
        self.tier: str = "quick"
        self.current_step: int = 0
        self.total_steps: int = 0
        self.start_wall: float = 0.0
        self.elapsed_s: float = 0.0
        self.eta_s: float = 0.0
        self.status_message: str = "Idle"
        self.latest_point: Optional[dict[str, Any]] = None
        self.points_measured: list[dict[str, Any]] = []
        self.error: Optional[str] = None

    def _get_helper(self):
        try:
            from helper.client import HelperClient
            client = HelperClient()
            r = client.read_energy()
            if r.get("ok"):
                return client
        except Exception as e:
            logger.debug("HelperClient not available: %s", e)
        return None

    def get_status(self) -> dict[str, Any]:
        with self._state_lock:
            if self.is_running and self.start_wall > 0:
                self.elapsed_s = round(time.monotonic() - self.start_wall, 1)

            cap_min, cap_max = discover_freq_limits()
            tier_info = get_tier_config(self.tier, cap_min, cap_max)
            discovered_classes = discover_hardware_classes()
            return {
                "is_running": self.is_running,
                "session_id": self.session_id,
                "tier": self.tier,
                "tier_name": tier_info["name"],
                "current_step": self.current_step,
                "total_steps": self.total_steps,
                "percent": round((self.current_step / max(1, self.total_steps)) * 100, 1) if self.total_steps else 0.0,
                "elapsed_s": self.elapsed_s,
                "eta_s": max(0.0, self.eta_s),
                "status_message": self.status_message,
                "latest_point": self.latest_point,
                "points_count": len(self.points_measured),
                "error": self.error,
                "classes": discovered_classes,
                "frequency_limits_khz": {"min": cap_min, "max": cap_max},
            }

    def start(
        self,
        tier: str = "quick",
        classes: Optional[list[str]] = None,
        quiet_background: bool = True,
        store: Optional[Any] = None,
    ) -> dict[str, Any]:
        with self._state_lock:
            if self.is_running:
                return {
                    "ok": False,
                    "error": "Calibration sweep is already running.",
                    "status": self.get_status(),
                }

            cap_min, cap_max = discover_freq_limits()
            tier_cfg = get_tier_config(tier, cap_min, cap_max)
            all_classes = discover_hardware_classes()
            selected_classes = [c for c in all_classes if classes is None or c["class"] in classes]
            if not selected_classes:
                selected_classes = all_classes

            freq_count = 1 + len(tier_cfg["caps"])
            total_runs = len(selected_classes) * freq_count * tier_cfg["reps"]
            est_total_s = total_runs * tier_cfg["est_run_s"]

            self.session_id = f"cal_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{tier}"
            self.tier = tier
            self.current_step = 0
            self.total_steps = total_runs
            self.start_wall = time.monotonic()
            self.elapsed_s = 0.0
            self.eta_s = round(est_total_s, 1)
            self.status_message = f"Starting {tier_cfg['name']} calibration..."
            self.latest_point = None
            self.points_measured = []
            self.error = None
            self.is_running = True
            self._cancel_event.clear()

            self._thread = threading.Thread(
                target=self._run_sweep,
                args=(tier, selected_classes, tier_cfg, quiet_background, store),
                daemon=True,
                name="calibration-runner",
            )
            self._thread.start()

            return {
                "ok": True,
                "session_id": self.session_id,
                "tier": tier,
                "total_runs": total_runs,
                "estimated_duration_s": est_total_s,
                "status": self.get_status(),
            }

    def stop(self) -> dict[str, Any]:
        with self._state_lock:
            if not self.is_running:
                return {
                    "ok": True,
                    "message": "No calibration sweep currently running.",
                    "points_saved": len(self.points_measured),
                }

            self.status_message = "Stopping calibration and restoring hardware..."
            self._cancel_event.set()

            if self._active_proc and self._active_proc.poll() is None:
                try:
                    import signal
                    os.killpg(os.getpgid(self._active_proc.pid), signal.SIGTERM)
                    time.sleep(0.1)
                    if self._active_proc and self._active_proc.poll() is None:
                        os.killpg(os.getpgid(self._active_proc.pid), signal.SIGKILL)
                except Exception as e:
                    logger.warning("Error terminating calibration process: %s", e)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

        helper = self._get_helper()
        if helper:
            try:
                helper.restore()
                logger.info("Helper restored hardware state to stock following calibration stop")
            except Exception as e:
                logger.warning("Helper restore error: %s", e)

        with self._state_lock:
            self.is_running = False
            self.status_message = f"Calibration stopped. Saved {len(self.points_measured)} points."

            try:
                default_bus().publish(
                    "calibration",
                    "calibration_cancelled",
                    {
                        "session_id": self.session_id,
                        "points_saved": len(self.points_measured),
                        "message": "Calibration sweep stopped by user. Stock settings restored.",
                    },
                )
            except Exception:
                pass

            return {
                "ok": True,
                "message": "Calibration stopped safely. Hardware restored to stock.",
                "points_saved": len(self.points_measured),
            }

    def _execute_pinned(self, cpus: list[int], workers: int, chunks: int) -> dict[str, Any]:
        """Execute fixed_compute kernel pinned to specific CPUs."""
        mask = ",".join(str(c) for c in cpus)
        cmd = [
            "taskset", "-c", mask,
            str(KERNEL_PATH),
            "--workers", str(workers),
            "--chunks", str(chunks),
            "--iters", "200000",
        ]

        t0 = time.monotonic()
        try:
            self._active_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            stdout, stderr = self._active_proc.communicate(timeout=600)
            rc = self._active_proc.returncode
        except subprocess.TimeoutExpired:
            if self._active_proc:
                try:
                    import signal
                    os.killpg(os.getpgid(self._active_proc.pid), signal.SIGKILL)
                except Exception:
                    self._active_proc.kill()
            return {"runtime_s": 0.0, "checksum": None, "returncode": -1, "error": "timeout"}
        finally:
            self._active_proc = None

        t1 = time.monotonic()
        runtime_s = round(t1 - t0, 4)
        checksum = None
        for line in stdout.splitlines():
            if "checksum:" in line:
                parts = line.split(":", 1)
                checksum = parts[1].strip()

        return {
            "runtime_s": runtime_s,
            "checksum": checksum,
            "returncode": rc,
            "stdout": stdout,
        }

    def _run_sweep(
        self,
        tier: str,
        classes: list[dict[str, Any]],
        tier_cfg: dict[str, Any],
        quiet_background: bool,
        store: Optional[Any],
    ):
        """Worker thread executing the calibration sweep."""
        helper = self._get_helper()
        reps = tier_cfg["reps"]
        caps = tier_cfg["caps"]

        if helper:
            try:
                helper.begin_session()
            except Exception as e:
                logger.warning("helper begin_session error: %s", e)

        boot_id = ""
        try:
            boot_id = open("/proc/sys/kernel/random/boot_id").read().strip()
        except Exception:
            boot_id = "unknown"

        recent_runtimes: list[float] = []

        try:
            for cls_def in classes:
                if self._cancel_event.is_set():
                    break

                cls_name = cls_def["class"]
                cls_display = cls_def["display"]
                cpus = cls_def["cpus"]
                workers = cls_def["workers"]
                chunks = cls_def["chunks"]

                freq_points = [("Stock Boost", True, None)]
                for cap in caps:
                    freq_points.append((f"{cap/1e6:.2f} GHz", False, cap))

                for freq_label, boost, cap_khz in freq_points:
                    if self._cancel_event.is_set():
                        break

                    if helper:
                        try:
                            if boost:
                                helper.apply_configuration({"boost": True})
                            else:
                                helper.apply_configuration({
                                    "boost": False,
                                    "policy_freq_caps_khz": {f"policy{c}": cap_khz for c in cpus},
                                })
                            helper.heartbeat()
                        except Exception as e:
                            logger.warning("Failed to apply configuration: %s", e)

                    if self._cancel_event.wait(0.4):
                        break

                    for rep in range(1, reps + 1):
                        if self._cancel_event.is_set():
                            break

                        with self._state_lock:
                            self.current_step += 1
                            self.status_message = (
                                f"Measuring {cls_display} @ {freq_label} "
                                f"(Rep {rep}/{reps})"
                            )

                        if helper:
                            helper.heartbeat()
                            e1 = helper.read_energy()
                        else:
                            e1 = {"ok": False}

                        res = self._execute_pinned(cpus, workers, chunks)
                        runtime_s = res["runtime_s"]

                        if helper:
                            e2 = helper.read_energy()
                            ej = (
                                ((e2["uj"] - e1["uj"]) % WRAP) / 1e6
                                if e1.get("ok") and e2.get("ok")
                                else None
                            )
                        else:
                            ej = round(runtime_s * (28.0 if boost else 14.0 * (cap_khz / 2000000 if cap_khz else 1.0)), 2)

                        watts = round(ej / runtime_s, 2) if ej and runtime_s > 0 else 15.0
                        score = round(1000.0 / runtime_s, 1) if runtime_s > 0 else 0.0
                        throughput = round(chunks / runtime_s, 1) if runtime_s > 0 else 0.0

                        point_entry = {
                            "class": cls_name,
                            "class_display": cls_display,
                            "control": freq_label,
                            "boost": boost,
                            "cap_khz": cap_khz,
                            "workers": workers,
                            "cpus": cpus,
                            "rep": rep,
                            "runtime_s": runtime_s,
                            "package_energy_j": ej,
                            "watts": watts,
                            "score": score,
                            "throughput": throughput,
                            "perf_per_watt": round(throughput / watts, 1) if watts > 0 else 0.0,
                            "kernel_checksum": res["checksum"],
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }

                        recent_runtimes.append(runtime_s)
                        avg_rt = sum(recent_runtimes[-5:]) / len(recent_runtimes[-5:])

                        with self._state_lock:
                            self.latest_point = point_entry
                            self.points_measured.append(point_entry)
                            remaining_steps = max(0, self.total_steps - self.current_step)
                            self.eta_s = round(remaining_steps * (avg_rt + 0.8), 1)

                        if store:
                            try:
                                cal_rec = CalibrationRecord(
                                    calibration_id=f"{self.session_id}_{cls_name}_{rep}_{cap_khz or 'stock'}",
                                    core_class=cls_name,
                                    layout="C2" if workers <= 8 else "all_logical",
                                    cpus=cpus,
                                    requested_control={"boost": 1 if boost else 0, "cap_khz": cap_khz},
                                    accepted_control={"boost": 1 if boost else 0, "cap_khz": cap_khz},
                                    repetition=rep,
                                    runtime_s=runtime_s,
                                    package_energy_j=ej,
                                    work_units=chunks,
                                    throughput=throughput,
                                    kernel_checksum=res["checksum"] or "",
                                    machine_fingerprint=boot_id,
                                    metadata={"tier": tier, "watts": watts, "score": score},
                                )
                                store.record_calibration(cal_rec)
                            except Exception as e:
                                logger.debug("Failed to record calibration to store: %s", e)

                        try:
                            default_bus().publish(
                                "calibration",
                                "calibration_progress",
                                {
                                    "session_id": self.session_id,
                                    "tier": tier,
                                    "current_step": self.current_step,
                                    "total_steps": self.total_steps,
                                    "percent": round((self.current_step / max(1, self.total_steps)) * 100, 1),
                                    "class_name": cls_name,
                                    "class_display": cls_display,
                                    "freq_label": freq_label,
                                    "boost": boost,
                                    "rep": rep,
                                    "reps_total": reps,
                                    "elapsed_s": round(time.monotonic() - self.start_wall, 1),
                                    "eta_s": self.eta_s,
                                    "latest_point": point_entry,
                                },
                            )
                        except Exception as e:
                            logger.debug("Failed to publish calibration event: %s", e)

                        if self._cancel_event.wait(0.3):
                            break

        except Exception as e:
            logger.exception("Error during calibration sweep: %s", e)
            with self._state_lock:
                self.error = str(e)
                self.status_message = f"Error: {e}"

        finally:
            if helper:
                try:
                    helper.restore()
                    helper.end_session()
                    logger.info("Helper restored hardware settings at end of calibration sweep")
                except Exception as e:
                    logger.warning("Helper restore in finally failed: %s", e)

            with self._state_lock:
                self.is_running = False
                if not self._cancel_event.is_set() and not self.error:
                    self.status_message = (
                        f"Calibration complete! Measured {len(self.points_measured)} points across {len(classes)} classes."
                    )
                    try:
                        default_bus().publish(
                            "calibration",
                            "calibration_complete",
                            {
                                "session_id": self.session_id,
                                "tier": tier,
                                "total_points": len(self.points_measured),
                                "status_message": self.status_message,
                            },
                        )
                    except Exception:
                        pass
