# API Specification — `joulectrl` (Frozen Contract v1)

**Owner:** Agent C (Dashboard & API)  
**Status:** Frozen contract (freeze by hour 3, per `AGENTS.md` §5)  
**Consumers:** Agent B (Core Engine / CLI), Agent C (Dashboard), Agent D (Integration & Explanations)

---

## 1. Architectural Invariants

1. **Host & Port:** Default bind to `127.0.0.1:8000`. Never expose to `0.0.0.0`.
2. **Single Origin:** The FastAPI backend serves the compiled Vite React frontend static assets from `/` or proxies in development, maintaining a single origin.
3. **Remote Access:** Via SSH port-forward / tunnel only (`ssh -L 8000:127.0.0.1:8000 ...`).
4. **No Arbitrary Commands:** No arbitrary shell commands or untrusted execution paths may be submitted via API.
5. **Restoration Safety:** Restoration state is always visible and verifiable via `/api/restore` and SSE events.

---

## 2. Route Table Summary

| Method | Path | Description | Spec Section |
|---|---|---|---|
| `GET` | `/api/capabilities` | Machine topology, powercap, driver controls, helper status | PLAN §8, §12 |
| `GET` | `/api/workloads` | List available workload plugins (e.g. clean_build, fixed_compute) | PLAN §8 |
| `POST` | `/api/experiments` | Create and initialize a new experiment session | PLAN §8 |
| `GET` | `/api/experiments` | List persisted experiments summary | PLAN §8, §11 |
| `GET` | `/api/experiments/{id}` | Get complete experiment record, runs, profile, selection, validation | PLAN §8 |
| `GET` | `/api/experiments/{id}/events` | SSE stream for real-time state, run progress, profile, selection | PLAN §8 |
| `POST` | `/api/experiments/{id}/select` | Re-run deterministic selection (budget or preference target) | PLAN §8, §6c |
| `POST` | `/api/experiments/{id}/validate` | Trigger fresh validation executions of baseline vs selected | PLAN §8, §11 |
| `POST` | `/api/experiments/{id}/cancel` | Abort active experiment, cancel run process group, restore settings | PLAN §8, §9 |
| `POST` | `/api/restore` | Emergency / manual restore of original CPU and power settings | PLAN §8, §9 |
| `POST` | `/api/explain` | Generate deterministic or LLM explanation for selection | PLAN §8, §10 |
| `GET` | `/api/experiments/{id}/export` | Export defensible, auditable JSON archive of experiment | PLAN §8 |
| `POST` | `/api/watch/start` | Start passive background power watcher (idle→task→idle) | AGENTS §6b, TEAM §4.5 |
| `POST` | `/api/watch/stop` | Stop passive watcher, return observed activity segments | AGENTS §6b, TEAM §4.5 |
| `GET` | `/api/watch/status` | Current watcher state, baseline power, active observations | AGENTS §6b, TEAM §4.5 |
| `GET` | `/api/watch/events` | SSE stream of watcher power samples, segment detection | AGENTS §6b, TEAM §4.5 |

---

## 3. Route Details and Data Contracts

### 3.1 Capabilities & Discovery

#### `GET /api/capabilities`
Returns discovered hardware capabilities, verified energy counters, and control tier.

**Response `200 OK`:**
```json
{
  "machine": {
    "hostname": "demo-laptop",
    "cpu_model": "AMD Ryzen AI 7 350",
    "boot_id": "9a12c8b0-...",
    "os": "Linux 6.10 Fedora",
    "tuned_active_profile": "throughput-performance"
  },
  "topology": {
    "logical_cores": 16,
    "physical_cores": 8,
    "classes": {
      "standard": [0, 2, 4, 6, 8, 10, 12, 14],
      "dense": [1, 3, 5, 7, 9, 11, 13, 15]
    },
    "driver": "amd-pstate-epp",
    "cpufreq_policies_count": 16
  },
  "energy": {
    "backend": "powercap_rapl",
    "domain": "package-0",
    "available": true,
    "root_required": true,
    "max_energy_uj": 65535000000,
    "unit": "joules"
  },
  "controls": {
    "boost_toggle": true,
    "frequency_caps": true,
    "epp_control": false,
    "effective_tier": "full"
  },
  "restoration": {
    "supported": true,
    "snapshot_present": false,
    "status": "restored"
  }
}
```

---

### 3.2 Workloads

#### `GET /api/workloads`
List registered workload plugins.

**Response `200 OK`:**
```json
[
  {
    "id": "clean_build",
    "name": "Repeatable Clean Compilation",
    "description": "Compiles benchmark workload with isolated build directories",
    "parameters": {
      "target": "default",
      "parallel_range": [1, 16]
    }
  },
  {
    "id": "fixed_compute",
    "name": "Fixed-work Compute Benchmark",
    "description": "Standardized compute kernel with deterministic checksum verification",
    "parameters": {
      "chunks": 64,
      "work_per_chunk": 100000
    }
  }
]
```

---

### 3.3 Experiments & Lifecycle

#### `POST /api/experiments`
Create and start an experiment.

**Request Body:**
```json
{
  "workload_id": "clean_build",
  "workload_params": {},
  "objective": "deadline",
  "runtime_budget_s": 45.0,
  "preference": {
    "energy_target_pct": 70.0,
    "perf_floor_pct": 90.0
  },
  "calibration_budget_s": 120.0,
  "headroom_pct": 5.0,
  "validation_selection": "pareto"
}
```
*Note on fields:*
- `objective`: `"deadline"` | `"preference"` | `"explore"` (AGENTS.md §6c)
- `runtime_budget_s`: float or null (for unlimited)
- `preference`: required if `objective == "preference"` (`energy_target_pct` and `perf_floor_pct`)
- `validation_selection`: `"pareto"` | `"all"` | array of explicit config IDs

**Response `201 Created`:**
```json
{
  "id": "exp_20260909_153000_a1b2",
  "state": "CHECKING",
  "created_at": "2026-09-09T10:00:00Z",
  "workload_id": "clean_build",
  "objective": "deadline",
  "runtime_budget_s": 45.0
}
```

#### `GET /api/experiments`
List all experiments (summary for dashboard history/sidebar).

**Response `200 OK`:**
```json
[
  {
    "id": "exp_20260909_153000_a1b2",
    "workload_id": "clean_build",
    "state": "COMPLETE",
    "created_at": "2026-09-09T10:00:00Z",
    "selected_config_id": "cfg_dense_4c_3000",
    "baseline_energy_j": 1250.4,
    "baseline_runtime_s": 42.1,
    "selected_energy_j": 875.2,
    "selected_runtime_s": 44.3,
    "energy_saved_pct": 30.0
  }
]
```

#### `GET /api/experiments/{id}`
Returns full experiment object including configuration points, runs, profile, selection, validation.

**Response `200 OK`:**
```json
{
  "id": "exp_20260909_153000_a1b2",
  "state": "COMPLETE",
  "created_at": "2026-09-09T10:00:00Z",
  "workload_id": "clean_build",
  "objective": "deadline",
  "runtime_budget_s": 45.0,
  "preference": null,
  "profile": {
    "baseline_config_id": "cfg_stock_all",
    "configurations": [
      {
        "id": "cfg_stock_all",
        "cpu_mask": "0-15",
        "workers": 16,
        "class_layout": "all_cores",
        "boost": true,
        "cap_khz": null,
        "median_runtime_s": 42.1,
        "guarded_runtime_s": 43.2,
        "runtime_spread_s": 1.1,
        "median_energy_j": 1250.4,
        "energy_spread_j": 25.0,
        "is_pareto": true,
        "runs": 3
      },
      {
        "id": "cfg_dense_4c_3000",
        "cpu_mask": "1,3,5,7",
        "workers": 4,
        "class_layout": "dense_physical",
        "boost": false,
        "cap_khz": 3000000,
        "median_runtime_s": 44.3,
        "guarded_runtime_s": 44.8,
        "runtime_spread_s": 0.5,
        "median_energy_j": 875.2,
        "energy_spread_j": 18.2,
        "is_pareto": true,
        "runs": 3
      }
    ]
  },
  "selection": {
    "config_id": "cfg_dense_4c_3000",
    "objective": "deadline",
    "status": "feasible_optimal",
    "runtime_budget_s": 45.0,
    "target_met": true,
    "savings_vs_baseline_pct": 30.0,
    "runtime_vs_baseline_pct": 5.2
  },
  "validation": {
    "status": "verified",
    "baseline_runs": [
      { "runtime_s": 42.0, "energy_j": 1248.0, "correct": true },
      { "runtime_s": 42.2, "energy_j": 1255.0, "correct": true },
      { "runtime_s": 42.1, "energy_j": 1251.0, "correct": true }
    ],
    "selected_runs": [
      { "runtime_s": 44.2, "energy_j": 870.0, "correct": true },
      { "runtime_s": 44.4, "energy_j": 880.0, "correct": true },
      { "runtime_s": 44.3, "energy_j": 875.0, "correct": true }
    ],
    "verified_savings_pct": 29.8,
    "verified_runtime_delta_s": 2.2
  },
  "restoration_status": "restored"
}
```

---

### 3.4 Selection and Tuning (Post-Profile)

#### `POST /api/experiments/{id}/select`
Re-evaluates the deterministic selector without re-running the workload.

**Request Body:**
```json
{
  "objective": "deadline",
  "runtime_budget_s": 46.0,
  "preference": {
    "energy_target_pct": 70.0,
    "perf_floor_pct": 90.0
  },
  "headroom_pct": 5.0
}
```

**Response `200 OK`:**
```json
{
  "config_id": "cfg_dense_4c_3000",
  "objective": "deadline",
  "status": "feasible_optimal",
  "reason": "Lowest-energy measured configuration meeting the empirical runtime rule",
  "metrics": {
    "median_runtime_s": 44.3,
    "guarded_runtime_s": 44.8,
    "median_energy_j": 875.2,
    "energy_savings_pct": 30.0
  },
  "preference_outcomes": {
    "energy_target_met": true,
    "perf_floor_met": true,
    "closest_energy_config_id": "cfg_dense_4c_3000",
    "closest_perf_config_id": "cfg_stock_all"
  }
}
```

---

### 3.5 Validation and Cancellation

#### `POST /api/experiments/{id}/validate`
Trigger fresh validation runs of the baseline vs selected configuration.

**Response `202 Accepted`:**
```json
{
  "status": "validation_started",
  "experiment_id": "exp_20260909_153000_a1b2",
  "planned_pairs": 3
}
```

#### `POST /api/experiments/{id}/cancel`
Cancels running experiment, signals the process group, restores power settings.

**Response `200 OK`:**
```json
{
  "status": "cancelling",
  "restoration": "restoring",
  "message": "Cancellation initiated. Workload process group terminated and CPU settings restoring."
}
```

---

### 3.6 Restoration

#### `POST /api/restore`
Emergency or manual restoration of CPU/energy settings.

**Response `200 OK`:**
```json
{
  "status": "restored",
  "verified": true,
  "details": "All cpufreq policies and boost states restored to original snapshot."
}
```

---

### 3.7 Explanations

#### `POST /api/explain`
Generate explanation for an experiment selection.

**Request Body:**
```json
{
  "experiment_id": "exp_20260909_153000_a1b2",
  "provider": "template"
}
```
*`provider` options:* `"template"` | `"local_llm"` | `"cloud_llm"` (PLAN §10). Default is `"template"`.

**Response `200 OK`:**
```json
{
  "experiment_id": "exp_20260909_153000_a1b2",
  "provider": "template",
  "text": "Selected cfg_dense_4c_3000 (4 Zen 5c cores, 3.0 GHz cap, boost disabled). Observed energy 875.2 J vs stock 1250.4 J (-30.0% package energy). Guarded runtime 44.8 s satisfies the 45.0 s budget.",
  "grounding_facts": [
    "Baseline package energy: 1250.4 J",
    "Selected package energy: 875.2 J (-30.0%)",
    "Baseline runtime: 42.1 s",
    "Selected runtime: 44.3 s (+5.2%)",
    "Budget: 45.0 s (guarded: 44.8 s)",
    "Restoration verified: yes"
  ]
}
```

---

### 3.8 Export

#### `GET /api/experiments/{id}/export`
Download complete auditable JSON archive.

**Response `200 OK` (Content-Type: `application/json`):**
Returns complete JSON document containing hardware fingerprint, raw calibration records, all run records with raw energy counter readings, configuration details, selection rationale, and validation measurements.

---

### 3.9 Watch Mode (Passive Idle-Activity-Idle Detection)

#### `POST /api/watch/start`
Starts the featherweight passive power watcher (0.5–1 Hz polling).

**Request Body:**
```json
{
  "poll_hz": 1.0,
  "onset_consecutive_s": 3,
  "idle_grace_s": 10
}
```

**Response `200 OK`:**
```json
{
  "status": "watching",
  "poll_hz": 1.0,
  "state": "calibrating_baseline",
  "message": "Watcher started. Learning idle baseline (30-60s genuine idle)."
}
```

#### `POST /api/watch/stop`
Stops passive watcher and returns recorded activity segments with suggested budgets.

**Response `200 OK`:**
```json
{
  "status": "stopped",
  "segments": [
    {
      "segment_id": "seg_01",
      "onset_timestamp": "2026-09-09T10:02:15Z",
      "end_timestamp": "2026-09-09T10:03:02Z",
      "duration_s": 47.0,
      "estimated_energy_j": 1410.0,
      "suggested_budget_s": 49.35,
      "mode": "watch",
      "note": "Estimated via idle-return detection. Uncertainty ±1.0s."
    }
  ]
}
```

#### `GET /api/watch/status`
Returns live state of watcher.

**Response `200 OK`:**
```json
{
  "active": true,
  "state": "monitoring",
  "current_power_w": 8.4,
  "baseline_median_w": 8.1,
  "baseline_spread_w": 0.5,
  "active_segment_elapsed_s": null,
  "completed_segments_count": 1
}
```

---

## 4. Server-Sent Events (SSE) Contract

### 4.1 Experiment Stream: `GET /api/experiments/{id}/events`

Format: standard SSE (`text/event-stream; charset=utf-8`).

```
event: <event_name>
data: <json_string>

```

#### SSE Event Names and Payloads

1. **`experiment_state`**  
   Fired on any state transition in the experiment state machine.
   ```json
   {
     "experiment_id": "exp_...",
     "state": "PROFILING",
     "previous_state": "PREPARING",
     "timestamp": "2026-09-09T10:01:00Z",
     "message": "Calibration verified. Starting workload profiling runs."
   }
   ```
   *States:* `IDLE`, `CHECKING`, `PREPARING`, `PROFILING`, `PROFILE_READY`, `SELECTED`, `VALIDATING`, `COMPLETE`, `CANCELLING`, `FAILED`, `RESTORING`, `RESTORED`, `RECOVERY_REQUIRED`.

2. **`run_progress`**  
   Fired during profiling or validation runs when a single execution begins or updates.
   ```json
   {
     "experiment_id": "exp_...",
     "phase": "profiling",
     "run_index": 4,
     "total_runs": 12,
     "config_id": "cfg_dense_4c_3000",
     "status": "running"
   }
   ```

3. **`run_complete`**  
   Fired immediately when a run finishes and raw counters are captured.
   ```json
   {
     "experiment_id": "exp_...",
     "phase": "profiling",
     "run_record": {
       "run_id": "run_4",
       "config_id": "cfg_dense_4c_3000",
       "runtime_s": 44.32,
       "package_energy_j": 875.2,
       "avg_power_w": 19.74,
       "exit_code": 0,
       "correct": true,
       "mode": "harness"
     }
   }
   ```

4. **`profile_ready`**  
   Fired when all profiling configurations have concluded.
   ```json
   {
     "experiment_id": "exp_...",
     "configurations_count": 12,
     "baseline_config_id": "cfg_stock_all",
     "summary": { "min_energy_j": 875.2, "fastest_runtime_s": 42.1 }
   }
   ```

5. **`selection_updated`**  
   Fired when a configuration is selected or budget/objective changes.
   ```json
   {
     "experiment_id": "exp_...",
     "selection": {
       "config_id": "cfg_dense_4c_3000",
       "objective": "deadline",
       "status": "feasible_optimal"
     }
   }
   ```

6. **`validation_progress`**  
   Fired during the validation phase.
   ```json
   {
     "experiment_id": "exp_...",
     "pair_index": 2,
     "total_pairs": 3,
     "current_phase": "selected_eval"
   }
   ```

7. **`validation_complete`**  
   Fired when fresh validation pairs complete.
   ```json
   {
     "experiment_id": "exp_...",
     "verified_savings_pct": 29.8,
     "verified_runtime_delta_s": 2.2,
     "status": "verified"
   }
   ```

8. **`restore_status`**  
   Fired whenever CPU settings are modified or restored.
   ```json
   {
     "status": "restored",
     "verified": true,
     "timestamp": "2026-09-09T10:05:00Z"
   }
   ```

9. **`error`**  
   Fired on unexpected runner or helper failures.
   ```json
   {
     "code": "HELPER_TIMEOUT",
     "message": "Privileged helper heartbeat lost. Triggered recovery.",
     "recoverable": false
   }
   ```

10. **`heartbeat`**  
    Keepalive comment (`: keepalive\n\n`) or event fired every 15s to keep connection alive through tunnels.

---

### 4.2 Watch Stream: `GET /api/watch/events`

Format: standard SSE (`text/event-stream; charset=utf-8`).

1. **`watch_sample`**  
   Emitted at ~1 Hz with current package power reading.
   ```json
   {
     "timestamp": "2026-09-09T10:02:20Z",
     "power_w": 24.5,
     "in_idle_band": false
   }
   ```

2. **`watch_segment`**  
   Emitted when an activity segment is detected, confirmed, and concluded.
   ```json
   {
     "segment_id": "seg_01",
     "onset_ts": "2026-09-09T10:02:15Z",
     "end_ts": "2026-09-09T10:03:02Z",
     "duration_s": 47.0,
     "estimated_energy_j": 1410.0,
     "suggested_budget_s": 49.35
   }
   ```

3. **`watch_state`**  
   Emitted when watcher state transitions (e.g. `idle` -> `task_detected` -> `in_grace_period` -> `task_ended`).
   ```json
   {
     "state": "active_task",
     "baseline_median_w": 8.1,
     "baseline_spread_w": 0.5
   }
   ```

---

## 5. Frozen Contract Guarantees

- **No drive-by renames:** Route names, SSE event names, and field schemas defined above are binding.
- **Backwards compatibility:** Any addition must be additive and optional.
- **Contract protocol:** Only Agent C edits this file. Any proposed changes will be preceded by consultation with Agent B and tagged with `[contract]` in `AGENTS.md`.
