export interface MachineInfo {
  hostname: string;
  cpu_model: string;
  boot_id: string;
  os: string;
  tuned_active_profile: string;
  ac_power: boolean;
}

export interface TopologyInfo {
  logical_cores: number;
  physical_cores: number;
  /** Class entries are either number[] (legacy fixture) or {cpus, hw_max_freq}
   *  (live discovery). Use classCpus() to read either shape. */
  classes: Record<string, number[] | { cpus?: number[]; hw_max_freq?: number }>;
  driver: string;
  governor: string;
  cpufreq_policies_count: number;
}

/** Read the CPU list from either class shape without crashing. */
export const classCpus = (v: number[] | { cpus?: number[] } | undefined | null): number[] =>
  Array.isArray(v) ? v : (v?.cpus ?? []);

export interface EnergyInfo {
  backend: string;
  domain: string;
  available: boolean;
  root_required: boolean;
  max_energy_uj: number;
  idle_watts: number;
  unit: string;
}

export interface CapabilitiesResponse {
  source?: 'live' | 'fixture';
  note?: string;
  machine: MachineInfo;
  topology: TopologyInfo;
  energy: EnergyInfo;
  controls: {
    boost_toggle: boolean;
    frequency_caps: boolean;
    epp_control: boolean;
    effective_tier: string;
  };
  restoration: {
    supported: boolean;
    snapshot_present: boolean;
    status: string;
  };
}

export interface WorkloadInfo {
  id: string;
  name: string;
  description: string;
  parameters: Record<string, any>;
}

export interface Configuration {
  id: string;
  layout: string;
  worker_count: number;
  cpu_affinity: number[];
  freq_cap_khz: number | null;
  boost: boolean | null;
  epp?: string | null;
}

export interface ConfigSummary {
  config_id: string;
  configuration: Configuration;
  runtime_samples: number[];
  energy_samples: number[];
  median_runtime_s: number;
  min_runtime_s: number;
  max_runtime_s: number;
  guarded_runtime_s: number;
  median_energy_j: number;
  min_energy_j: number;
  max_energy_j: number;
  median_power_w: number;
  profile_is_usable: boolean;
  total_runs: number;
  is_baseline: boolean;
}

export interface RunRecord {
  run_id: string;
  experiment_id: string;
  config_id: string;
  workload_name: string;
  repetition: number;
  mode: string;
  phase: string;
  runtime_s: number;
  package_energy_j: number | null;
  avg_power_w?: number | null;
  status: string;
  exit_code: number;
  output_verified: boolean;
  configuration?: Configuration;
}

export interface Selection {
  config_id: string;
  selected_config_id?: string;
  configuration?: Configuration;
  objective: string;
  status: string;
  status_message?: string;
  runtime_budget_s?: number | null;
  target_met?: boolean;
  savings_vs_baseline_pct?: number;
  runtime_vs_baseline_pct?: number;
  energy_reduction_pct?: number;
  runtime_increase_pct?: number;
  deadline_s?: number;
  selected_median_energy_j?: number;
  selected_median_runtime_s?: number;
  selected_guarded_runtime_s?: number;
  baseline_config_id?: string;
  baseline_median_energy_j?: number;
  baseline_median_runtime_s?: number;
  frontier_config_ids?: string[];
  metrics?: {
    median_runtime_s: number;
    guarded_runtime_s: number;
    median_energy_j: number;
    energy_savings_pct: number;
    task_duration_s?: number | null;
    projected_runtime_s?: number | null;
    projected_guarded_runtime_s?: number | null;
    projected_energy_j?: number | null;
  };
  task_duration_s?: number | null;
  projected_runtime_s?: number | null;
  projected_guarded_runtime_s?: number | null;
  projected_energy_j?: number | null;
  preference_outcomes?: {
    energy_target_met: boolean;
    perf_floor_met: boolean;
    closest_energy_config_id: string;
    closest_perf_config_id: string;
  };
}

export interface ValidationPair {
  pair_index: number;
  baseline_run: RunRecord;
  selected_run: RunRecord;
  runtime_difference_pct: number;
  energy_reduction_pct: number;
  met_budget: boolean;
  both_succeeded: boolean;
}

export interface Profile {
  experiment_id: string;
  workload_name: string;
  baseline_config_id: string;
  configurations: Record<string, ConfigSummary>;
  runs: RunRecord[];
  validity_state: string;
  margin: number;
  suggested_budget_s?: number | null;
}

export interface Experiment {
  id: string;
  state: string;
  created_at: string;
  workload_id: string;
  objective: string;
  runtime_budget_s?: number | null;
  task_duration_s?: number | null;
  preference?: {
    energy_target_pct: number;
    perf_floor_pct: number;
  };
  profile: Profile;
  selection: Selection;
  validation: {
    status: string;
    pairs: ValidationPair[];
    verified_savings_pct: number | null;
    verified_runtime_delta_s: number | null;
  };
  restoration_status: string;
}

export interface WatchSavingsReceipt {
  session_id: number;
  timestamp: string;
  runtime_s: number;
  actual_energy_j: number | null;
  estimated_stock_j: number | null;
  saved_energy_j: number | null;
  saved_pct: number;
  target_pid?: number | null;
  target_process_name?: string | null;
}

export interface WatchStatus {
  active: boolean;
  state: string;
  source?: {
    source: string;
    domain: string;
    synthetic: boolean;
    note?: string;
  } | null;
  poll_hz?: number | null;
  current_power_w: number | null;
  baseline_median_w: number | null;
  baseline_spread_w: number | null;
  threshold_w?: number | null;
  active_segment_elapsed_s: number | null;
  completed_segments_count: number;
  active_control?: boolean;
  control_state?: string;
  optimization_objective?: 'efficiency' | 'deadline' | 'performance';
  recurrence_mode?: 'repeated' | 'once';
  time_budget_s?: number | null;
  target_freq_khz?: number | null;
  target_pid?: number | null;
  target_process_name?: string | null;
  target_command?: string | null;
  total_saved_energy_j?: number;
  active_sessions_count?: number;
  savings_history?: WatchSavingsReceipt[];
}

export interface SavingsSummary {
  sessions_count: number;
  total_runtime_s: number;
  total_stock_energy_j: number;
  total_optimized_energy_j: number;
  total_saved_energy_j: number;
  total_saved_energy_wh: number;
  total_saved_energy_kwh: number;
  avg_saved_pct: number;
  avg_watts_saved: number;
  battery_extension_minutes: number;
  co2_saved_grams: number;
}

export interface SavingsLedgerEntry {
  id: number;
  session_id: string;
  source: string;
  workload_name?: string | null;
  app_name?: string | null;
  target_pid?: number | null;
  objective?: string | null;
  runtime_s: number;
  stock_energy_j: number;
  optimized_energy_j: number;
  saved_energy_j: number;
  saved_pct: number;
  stock_avg_power_w?: number | null;
  optimized_avg_power_w?: number | null;
  saved_avg_power_w?: number | null;
  timestamp_iso: string;
  metadata?: Record<string, any>;
}

export interface SavingsDashboardResponse {
  ok: boolean;
  opted_in: boolean;
  summary: SavingsSummary;
  ledger: SavingsLedgerEntry[];
  zero_power_architecture: {
    idle_polling_overhead_w: number;
    event_driven: boolean;
    ledger_storage: string;
    description: string;
  };
}

