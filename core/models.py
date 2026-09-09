"""core/models.py — frozen data contracts for joulectrl (Agent B owned).

Non-negotiable contract invariants:
1. Hardware counter package energy only — never relabel a core-only counter as package energy.
2. Missing energy is None / unavailable, NEVER 0.
3. Monotonic clock for all runtimes.
4. Watch-mode records carry mode="watch" and detection metadata, excluded from Pareto evidence by default.
5. CalibrationRecords carry requested and accepted control levels per row.
6. Objective modes: "deadline", "preference" (§6c), and "frontier".
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def utc_now_iso() -> str:
    """Return ISO-8601 formatted UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Topology & Hardware Capability Models
# ---------------------------------------------------------------------------

@dataclass
class CpuCore:
    """Represents a single logical CPU and its hardware topology attributes."""
    cpu_id: int
    physical_core_id: int
    socket_id: int = 0
    smt_siblings: list[int] = field(default_factory=list)
    cpuinfo_max_freq_khz: Optional[int] = None
    cpuinfo_min_freq_khz: Optional[int] = None
    cpufreq_policy_id: Optional[int] = None
    core_class: Optional[str] = None  # e.g. "zen5", "zen5c", "fast", "efficient"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CpuCore:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class CpuTopology:
    """CPU topology discovered on the machine."""
    sockets: list[int] = field(default_factory=lambda: [0])
    physical_cores: int = 0
    logical_cpus: int = 0
    cpus: dict[int, CpuCore] = field(default_factory=dict)
    smt_active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "sockets": self.sockets,
            "physical_cores": self.physical_cores,
            "logical_cpus": self.logical_cpus,
            "smt_active": self.smt_active,
            "cpus": {str(k): v.to_dict() if isinstance(v, CpuCore) else v for k, v in self.cpus.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CpuTopology:
        cpus_raw = data.get("cpus", {})
        parsed_cpus: dict[int, CpuCore] = {}
        for k, v in cpus_raw.items():
            parsed_cpus[int(k)] = CpuCore.from_dict(v) if isinstance(v, dict) else v
        return cls(
            sockets=data.get("sockets", [0]),
            physical_cores=data.get("physical_cores", 0),
            logical_cpus=data.get("logical_cpus", 0),
            smt_active=data.get("smt_active", True),
            cpus=parsed_cpus,
        )


@dataclass
class CoreClassMap:
    """Mapping of discovered CPU classes and execution layouts."""
    classes: dict[str, list[int]] = field(default_factory=dict)  # class_name -> list of logical CPU IDs
    layouts: dict[str, list[int]] = field(default_factory=dict)  # 'A', 'B', 'C', 'D' -> list of logical CPU IDs
    fast_class: str = ""
    efficient_class: str = ""
    is_heterogeneous: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CoreClassMap:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class CapabilityReport:
    """Report of verified machine capabilities from discovery / Gate A."""
    machine_fingerprint: str
    cpu_model: str
    topology: CpuTopology
    classes: CoreClassMap
    energy_backend_name: str
    energy_scope: str = "package-0"
    energy_unit: str = "uj"
    energy_counter_range_uj: Optional[int] = None
    energy_requires_root: bool = False
    control_tier: str = "full"  # "full", "reduced", "measurement_only", "timing_only"
    cpufreq_driver: str = ""
    num_policies: int = 0
    supported_controls: list[str] = field(default_factory=list)
    boost_path_exists: bool = False
    boost_required_for_caps: bool = False
    epp_available: bool = False
    epp_effective: bool = False
    tuned_profile: Optional[str] = None
    governor: str = ""
    warnings: list[str] = field(default_factory=list)
    timestamp_iso: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["topology"] = self.topology.to_dict()
        d["classes"] = self.classes.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CapabilityReport:
        clean = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        if "topology" in clean and isinstance(clean["topology"], dict):
            clean["topology"] = CpuTopology.from_dict(clean["topology"])
        if "classes" in clean and isinstance(clean["classes"], dict):
            clean["classes"] = CoreClassMap.from_dict(clean["classes"])
        return cls(**clean)


# ---------------------------------------------------------------------------
# Configuration Model
# ---------------------------------------------------------------------------

@dataclass
class Configuration:
    """Concrete hardware/software execution configuration."""
    id: str
    layout: str  # e.g. "A", "B", "C", "D", "baseline", "stock"
    worker_count: int
    cpu_affinity: list[int] = field(default_factory=list)
    freq_cap_khz: Optional[int] = None
    policy_freq_caps_khz: dict[int, int] = field(default_factory=dict)
    boost: Optional[bool] = None  # True=enabled, False=disabled, None=unchanged
    epp: Optional[str] = None  # e.g. "performance", "balance_performance", etc.
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Configuration:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Execution & Measurement Records
# ---------------------------------------------------------------------------

@dataclass
class RunRecord:
    """A single execution run measurement.
    
    Invariants:
    - package_energy_j is None when unavailable, NEVER 0.0.
    - mode is "harness" or "watch".
    - watch mode records carry detection metadata.
    """
    run_id: str
    experiment_id: str
    config_id: str
    workload_name: str
    repetition: int
    mode: str = "harness"  # "harness" | "watch"
    phase: str = "profiling"  # "profiling" | "validation" | "calibration" | "watch"
    
    # Timing (monotonic clock)
    start_time_monotonic: float = 0.0
    end_time_monotonic: float = 0.0
    runtime_s: float = 0.0
    
    # Energy: Package energy from verified hardware counter
    package_energy_j: Optional[float] = None
    start_energy_uj: Optional[int] = None
    end_energy_uj: Optional[int] = None
    energy_available: bool = True
    avg_power_w: Optional[float] = None
    
    # Execution status
    status: str = "success"  # "success" | "failed" | "timeout" | "cancelled"
    exit_code: Optional[int] = 0
    output_verified: bool = True
    checksum: Optional[str] = None
    error_message: Optional[str] = None
    
    # Watch-mode metadata (§6b)
    idle_baseline_w: Optional[float] = None
    idle_spread_w: Optional[float] = None
    onset_ts: Optional[float] = None
    end_ts: Optional[float] = None
    poll_interval_s: Optional[float] = None
    detection_uncertainty_s: Optional[float] = None
    watch_note: Optional[str] = None
    
    # Configuration snapshot & timestamp
    configuration: Optional[Configuration] = None
    timestamp_iso: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Non-negotiable safety guard:
        # If energy is unavailable, package_energy_j must be None, never 0.0
        if not self.energy_available and self.package_energy_j is not None:
            self.package_energy_j = None
        # Auto-compute average power if runtime > 0 and energy is valid
        if self.avg_power_w is None and self.package_energy_j is not None and self.runtime_s > 0:
            self.avg_power_w = self.package_energy_j / self.runtime_s

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.configuration is not None:
            d["configuration"] = self.configuration.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunRecord:
        clean = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        if "configuration" in clean and isinstance(clean["configuration"], dict):
            clean["configuration"] = Configuration.from_dict(clean["configuration"])
        clean.setdefault("experiment_id", data.get("experiment_id", ""))
        clean.setdefault("workload_name", data.get("workload_name", "clean_build"))
        return cls(**clean)


@dataclass
class CalibrationRecord:
    """Row from the dense per-class calibration sweep (§6)."""
    calibration_id: str
    core_class: str  # e.g. "fast", "efficient"
    layout: str  # "C1" (single-core baseline) or "C2" (parallel scaling)
    cpus: list[int] = field(default_factory=list)
    requested_control: dict[str, Any] = field(default_factory=dict)  # requested control level
    accepted_control: dict[str, Any] = field(default_factory=dict)   # readback accepted level
    phase: str = "calibration"
    repetition: int = 1
    
    # Timing & Energy
    runtime_s: float = 0.0
    package_energy_j: Optional[float] = None
    energy_available: bool = True
    avg_power_w: Optional[float] = None
    
    # Throughput & Scaling efficiency
    work_units: float = 0.0
    throughput: float = 0.0  # work_units / runtime_s
    scaling_efficiency: Optional[float] = None  # parallel throughput / (workers * C1 single-core throughput)
    
    kernel_checksum: str = ""
    machine_fingerprint: str = ""
    timestamp_iso: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.energy_available and self.package_energy_j is not None:
            self.package_energy_j = None
        if self.avg_power_w is None and self.package_energy_j is not None and self.runtime_s > 0:
            self.avg_power_w = self.package_energy_j / self.runtime_s
        if self.throughput == 0.0 and self.runtime_s > 0 and self.work_units > 0:
            self.throughput = self.work_units / self.runtime_s

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CalibrationRecord:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Profile & Aggregation Models
# ---------------------------------------------------------------------------

@dataclass
class ConfigSummary:
    """Aggregated metrics across repetitions of a configuration in a profile."""
    config_id: str
    configuration: Configuration
    runtime_samples: list[float] = field(default_factory=list)
    energy_samples: list[float] = field(default_factory=list)
    
    median_runtime_s: float = 0.0
    min_runtime_s: float = 0.0
    max_runtime_s: float = 0.0
    guarded_runtime_s: float = 0.0  # max(runtime_samples) * (1 + margin)
    
    median_energy_j: Optional[float] = None
    min_energy_j: Optional[float] = None
    max_energy_j: Optional[float] = None
    
    median_power_w: Optional[float] = None
    
    profile_is_usable: bool = True
    failure_count: int = 0
    total_runs: int = 0
    is_baseline: bool = False
    rejection_reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["configuration"] = self.configuration.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConfigSummary:
        clean = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        if "configuration" in clean and isinstance(clean["configuration"], dict):
            clean["configuration"] = Configuration.from_dict(clean["configuration"])
        return cls(**clean)


@dataclass
class Profile:
    """Collection of measured configurations and runs for an experiment."""
    experiment_id: str
    workload_name: str
    baseline_config_id: str
    configurations: dict[str, ConfigSummary] = field(default_factory=dict)
    runs: list[RunRecord] = field(default_factory=list)
    machine_fingerprint: str = ""
    validity_state: str = "valid"  # "valid", "invalidated", "unvalidated"
    created_at_iso: str = field(default_factory=utc_now_iso)
    margin: float = 0.05
    suggested_budget_s: Optional[float] = None  # Pre-filled from watch mode if available

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "workload_name": self.workload_name,
            "baseline_config_id": self.baseline_config_id,
            "machine_fingerprint": self.machine_fingerprint,
            "validity_state": self.validity_state,
            "created_at_iso": self.created_at_iso,
            "margin": self.margin,
            "suggested_budget_s": self.suggested_budget_s,
            "configurations": {k: v.to_dict() for k, v in self.configurations.items()},
            "runs": [r.to_dict() for r in self.runs],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Profile:
        configs_raw = data.get("configurations", {})
        parsed_configs = {k: ConfigSummary.from_dict(v) for k, v in configs_raw.items()}
        runs_raw = data.get("runs", [])
        parsed_runs = [RunRecord.from_dict(r) for r in runs_raw]
        return cls(
            experiment_id=data.get("experiment_id", ""),
            workload_name=data.get("workload_name", ""),
            baseline_config_id=data.get("baseline_config_id", ""),
            configurations=parsed_configs,
            runs=parsed_runs,
            machine_fingerprint=data.get("machine_fingerprint", ""),
            validity_state=data.get("validity_state", "valid"),
            created_at_iso=data.get("created_at_iso", utc_now_iso()),
            margin=data.get("margin", 0.05),
            suggested_budget_s=data.get("suggested_budget_s"),
        )


# ---------------------------------------------------------------------------
# Optimizer Selection & Validation
# ---------------------------------------------------------------------------

@dataclass
class Selection:
    """Optimizer selection result across candidate configurations.
    
    Supports:
    - Deadline mode: min energy subject to guarded_runtime <= deadline_s
    - Preference mode (§6c): min energy meeting energy_target_pct and perf_floor_pct
    - Frontier mode: Pareto non-dominated configurations
    """
    experiment_id: str
    objective_mode: str  # "deadline" | "preference" | "frontier"
    status: str  # "selected", "no_feasible_point", "baseline_already_optimal", "within_noise", "profile_unusable", "unvalidated"
    status_message: str
    
    # Selected configuration
    selected_config_id: Optional[str] = None
    selected_configuration: Optional[Configuration] = None
    selected_median_energy_j: Optional[float] = None
    selected_guarded_runtime_s: Optional[float] = None
    selected_median_runtime_s: Optional[float] = None
    
    # Baseline comparison
    baseline_config_id: Optional[str] = None
    baseline_median_energy_j: Optional[float] = None
    baseline_median_runtime_s: Optional[float] = None
    
    # Percentage comparisons
    energy_reduction_pct: Optional[float] = None  # 100 * (1 - E_sel / E_base)
    runtime_increase_pct: Optional[float] = None  # 100 * (T_sel / T_base - 1)
    
    # Deadline mode fields
    deadline_s: Optional[float] = None
    margin: float = 0.05
    
    # Preference mode fields (§6c)
    energy_target_pct: Optional[float] = None  # e.g. 70.0 (<= 70% baseline energy)
    perf_floor_pct: Optional[float] = None      # e.g. 90.0 (>= 90% baseline speed)
    preference_outcome_state: Optional[str] = None  # "both_met", "closest_perf_floor", "closest_energy_target", "none_feasible"
    perf_floor_miss_pct: Optional[float] = None
    energy_target_miss_pct: Optional[float] = None
    
    # Frontier / candidate sets
    frontier_config_ids: list[str] = field(default_factory=list)
    candidate_summaries: list[dict[str, Any]] = field(default_factory=list)
    created_at_iso: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.selected_configuration is not None:
            d["selected_configuration"] = self.selected_configuration.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Selection:
        clean = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        if "selected_configuration" in clean and isinstance(clean["selected_configuration"], dict):
            clean["selected_configuration"] = Configuration.from_dict(clean["selected_configuration"])
        return cls(**clean)


@dataclass
class ValidationPair:
    """An independent execution pair: fresh baseline vs fresh selected candidate."""
    pair_index: int
    baseline_run: RunRecord
    selected_run: RunRecord
    runtime_difference_pct: Optional[float] = None  # 100 * (T_sel / T_base - 1)
    energy_reduction_pct: Optional[float] = None    # 100 * (1 - E_sel / E_base)
    met_budget: bool = False
    both_succeeded: bool = True
    live: bool = False  # True if live presentation pair; False if prepared repeated validation

    def __post_init__(self) -> None:
        self.both_succeeded = (self.baseline_run.status == "success" and self.selected_run.status == "success")
        if self.baseline_run.runtime_s > 0:
            self.runtime_difference_pct = 100.0 * (self.selected_run.runtime_s / self.baseline_run.runtime_s - 1.0)
        if (self.baseline_run.package_energy_j is not None 
                and self.baseline_run.package_energy_j > 0 
                and self.selected_run.package_energy_j is not None):
            self.energy_reduction_pct = 100.0 * (1.0 - self.selected_run.package_energy_j / self.baseline_run.package_energy_j)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair_index": self.pair_index,
            "baseline_run": self.baseline_run.to_dict(),
            "selected_run": self.selected_run.to_dict(),
            "runtime_difference_pct": self.runtime_difference_pct,
            "energy_reduction_pct": self.energy_reduction_pct,
            "met_budget": self.met_budget,
            "both_succeeded": self.both_succeeded,
            "live": self.live,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ValidationPair:
        return cls(
            pair_index=data.get("pair_index", 0),
            baseline_run=RunRecord.from_dict(data["baseline_run"]),
            selected_run=RunRecord.from_dict(data["selected_run"]),
            runtime_difference_pct=data.get("runtime_difference_pct"),
            energy_reduction_pct=data.get("energy_reduction_pct"),
            met_budget=data.get("met_budget", False),
            both_succeeded=data.get("both_succeeded", True),
            live=data.get("live", False),
        )
