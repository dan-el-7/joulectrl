import { CapabilitiesResponse, Experiment, Selection, WatchStatus, WorkloadInfo } from './types';

const API_BASE = '/api';

export async function fetchCapabilities(): Promise<CapabilitiesResponse> {
  const res = await fetch(`${API_BASE}/capabilities`);
  if (!res.ok) throw new Error(`Failed to fetch capabilities: ${res.statusText}`);
  return res.json();
}

export async function fetchWorkloads(): Promise<WorkloadInfo[]> {
  const res = await fetch(`${API_BASE}/workloads`);
  if (!res.ok) throw new Error(`Failed to fetch workloads: ${res.statusText}`);
  return res.json();
}

export async function fetchExperiments(): Promise<any[]> {
  const res = await fetch(`${API_BASE}/experiments`);
  if (!res.ok) throw new Error(`Failed to fetch experiments: ${res.statusText}`);
  return res.json();
}

export async function fetchExperiment(id: string): Promise<Experiment> {
  const res = await fetch(`${API_BASE}/experiments/${id}`);
  if (!res.ok) throw new Error(`Failed to fetch experiment ${id}: ${res.statusText}`);
  return res.json();
}

export async function createExperiment(payload: {
  workload_id: string;
  objective: string;
  runtime_budget_s?: number | null;
  preference?: { energy_target_pct: number; perf_floor_pct: number };
  calibration_budget_s?: number | null;
  experimental_passive_caps?: boolean;
  repetitions?: number;
  priority_mode?: string;
}): Promise<{ id: string }> {
  const res = await fetch(`${API_BASE}/experiments`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Failed to create experiment: ${res.statusText}`);
  return res.json();
}

export async function reselectConfiguration(
  experimentId: string,
  payload: {
    objective: string;
    runtime_budget_s?: number | null;
    preference?: { energy_target_pct: number; perf_floor_pct: number };
    headroom_pct?: number;
  }
): Promise<Selection> {
  const res = await fetch(`${API_BASE}/experiments/${experimentId}/select`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Failed to reselect: ${res.statusText}`);
  return res.json();
}

export async function validateExperiment(experimentId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/experiments/${experimentId}/validate`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`Failed to validate: ${res.statusText}`);
  return res.json();
}

export async function cancelExperiment(experimentId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/experiments/${experimentId}/cancel`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`Failed to cancel experiment: ${res.statusText}`);
  return res.json();
}

export async function restoreSettings(): Promise<any> {
  const res = await fetch(`${API_BASE}/restore`, { method: 'POST' });
  if (!res.ok) throw new Error(`Failed to restore: ${res.statusText}`);
  return res.json();
}

export async function explainSelection(
  experimentId: string,
  provider: string = 'template',
  model?: string,
  ollamaUrl?: string,
): Promise<any> {
  const payload: Record<string, any> = { experiment_id: experimentId, provider };
  if (model) payload.model = model;
  if (ollamaUrl) payload.ollama_url = ollamaUrl;

  const res = await fetch(`${API_BASE}/explain`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Failed to generate explanation: ${res.statusText}`);
  return res.json();
}

export interface OllamaModelInfo {
  name: string;
  size_mb?: number;
  modified_at?: string;
  parameter_size?: string;
  quantization_level?: string;
  family?: string;
}

export interface OllamaScanResponse {
  connected: boolean;
  url: string;
  models: OllamaModelInfo[];
  count: number;
  message: string;
}

export async function fetchOllamaModels(url: string = 'http://localhost:11434'): Promise<OllamaScanResponse> {
  const res = await fetch(`${API_BASE}/llm/models?url=${encodeURIComponent(url)}`);
  if (!res.ok) throw new Error(`Failed to scan Ollama models: ${res.statusText}`);
  return res.json();
}

export async function testOllamaModel(url: string, model: string): Promise<{ ok: boolean; latency_ms: number; response?: string; error?: string }> {
  const res = await fetch(`${API_BASE}/llm/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, model }),
  });
  if (!res.ok) throw new Error(`Failed to test model: ${res.statusText}`);
  return res.json();
}

export async function fetchValidationPoints(experimentId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/experiments/${experimentId}/validation-points`);
  if (!res.ok) throw new Error(`Failed to fetch validation points: ${res.statusText}`);
  return res.json();
}

export async function fetchCalibration(experimentId?: string): Promise<any> {
  const url = experimentId
    ? `${API_BASE}/calibration?experiment_id=${encodeURIComponent(experimentId)}`
    : `${API_BASE}/calibration`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch calibration: ${res.statusText}`);
  return res.json();
}

export async function fetchWatchStatus(): Promise<WatchStatus> {
  const res = await fetch(`${API_BASE}/watch/status`);
  if (!res.ok) throw new Error(`Failed to fetch watch status: ${res.statusText}`);
  return res.json();
}

export async function startWatch(params?: { poll_hz?: number; onset_consecutive_s?: number; idle_grace_s?: number }): Promise<any> {
  const res = await fetch(`${API_BASE}/watch/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      poll_hz: params?.poll_hz ?? 1.0,
      onset_consecutive_s: params?.onset_consecutive_s ?? 3,
      idle_grace_s: params?.idle_grace_s ?? 18,
    }),
  });
  if (!res.ok) throw new Error(`Failed to start watch: ${res.statusText}`);
  return res.json();
}

export async function stopWatch(): Promise<any> {
  const res = await fetch(`${API_BASE}/watch/stop`, { method: 'POST' });
  if (!res.ok) throw new Error(`Failed to stop watch: ${res.statusText}`);
  return res.json();
}

export interface DetectedApp {
  key: string;
  name: string;
  pids: number[];
  process_count: number;
  total_cpu_pct: number;
  total_mem_pct: number;
}

export interface UnclassifiedProcess {
  pid: number;
  name: string;
  cpu_pct: number;
  mem_pct: number;
  cmdline: string;
}

export interface SystemNoiseStatus {
  is_quiet: boolean;
  total_noise_cpu_pct: number;
  detected_apps: DetectedApp[];
  unclassified_processes: UnclassifiedProcess[];
}

export interface QuietSystemResult {
  ok: boolean;
  terminated_pids: number[];
  closed_apps: string[];
  remaining_noise: SystemNoiseStatus;
}

export async function fetchSystemNoise(): Promise<SystemNoiseStatus> {
  const res = await fetch(`${API_BASE}/system/noise`);
  if (!res.ok) throw new Error(`Failed to fetch system noise: ${res.statusText}`);
  return res.json();
}

export async function quietSystem(appKeys?: string[], pids?: number[]): Promise<QuietSystemResult> {
  const res = await fetch(`${API_BASE}/system/quiet`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ app_keys: appKeys, pids }),
  });
  if (!res.ok) throw new Error(`Failed to quiet system: ${res.statusText}`);
  return res.json();
}

export interface SystemThermalStatus {
  cpu_temp_c: number | null;
  is_throttling: boolean;
  warning_level: 'normal' | 'elevated' | 'critical';
  message: string;
  source: string;
}

export async function fetchSystemThermal(): Promise<SystemThermalStatus> {
  const res = await fetch(`${API_BASE}/system/thermal`);
  if (!res.ok) throw new Error(`Failed to fetch thermal status: ${res.statusText}`);
  return res.json();
}

export interface UserProcess {
  pid: number;
  ppid: number;
  user: string;
  name: string;
  cmdline: string;
  cpu_pct: number;
  mem_pct: number;
  nice: number;
  affinity: string;
  affinity_label: string;
}

export interface UserProcessesResponse {
  processes: UserProcess[];
  total: number;
}

export async function fetchUserProcesses(limit = 100): Promise<UserProcessesResponse> {
  const res = await fetch(`${API_BASE}/system/processes?limit=${limit}`);
  if (!res.ok) throw new Error(`Failed to fetch processes: ${res.statusText}`);
  return res.json();
}

export async function setProcessPriority(params: {
  pid?: number;
  pattern?: string;
  policy: 'deprioritize_eco' | 'prioritize_fast' | 'restore_normal';
}): Promise<any> {
  const res = await fetch(`${API_BASE}/system/process-priority`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(`Failed to set process priority: ${res.statusText}`);
  return res.json();
}

export interface FocusSwitchResponse {
  ok: boolean;
  mode: 'reverse' | 'off' | 'on';
  target_pid?: number | null;
  target_pattern?: string | null;
  actions_taken?: string[];
  message: string;
}

export async function fetchFocusSwitch(): Promise<FocusSwitchResponse> {
  const res = await fetch(`${API_BASE}/system/focus-switch`);
  if (!res.ok) throw new Error(`Failed to fetch focus switch state: ${res.statusText}`);
  return res.json();
}

export async function setFocusSwitch(params: {
  mode: 'reverse' | 'off' | 'on';
  target_pid?: number | null;
  target_pattern?: string | null;
}): Promise<FocusSwitchResponse> {
  const res = await fetch(`${API_BASE}/system/focus-switch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(`Failed to set focus switch: ${res.statusText}`);
  return res.json();
}

export type CalibrationTier = 'quick' | 'standard' | 'exhaustive';

export interface DiscoveredClassInfo {
  class: string;
  display: string;
  cpus: number[];
  workers: number;
  chunks?: number;
}

export interface CalibrationStatusResponse {
  is_running: boolean;
  session_id?: string | null;
  tier: CalibrationTier;
  tier_name: string;
  current_step: number;
  total_steps: number;
  percent: number;
  elapsed_s: number;
  eta_s: number;
  status_message: string;
  latest_point?: any;
  points_count: number;
  error?: string | null;
  classes?: DiscoveredClassInfo[];
  frequency_limits_khz?: { min: number; max: number };
}

export async function fetchCalibrationStatus(): Promise<CalibrationStatusResponse> {
  const res = await fetch(`${API_BASE}/calibration/status`);
  if (!res.ok) throw new Error(`Failed to fetch calibration status: ${res.statusText}`);
  return res.json();
}

export async function startCalibration(params: {
  tier: CalibrationTier;
  classes?: string[];
  quiet_background?: boolean;
}): Promise<any> {
  const res = await fetch(`${API_BASE}/calibration/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to start calibration');
  }
  return res.json();
}

export async function stopCalibration(): Promise<{ ok: boolean; message: string; points_saved: number }> {
  const res = await fetch(`${API_BASE}/calibration/stop`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`Failed to stop calibration: ${res.statusText}`);
  return res.json();
}
