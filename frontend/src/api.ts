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
  calibration_budget_s?: number;
  experimental_passive_caps?: boolean;
  repetitions?: number;
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

export async function restoreSettings(): Promise<any> {
  const res = await fetch(`${API_BASE}/restore`, { method: 'POST' });
  if (!res.ok) throw new Error(`Failed to restore: ${res.statusText}`);
  return res.json();
}

export async function explainSelection(experimentId: string, provider: string = 'template'): Promise<any> {
  const res = await fetch(`${API_BASE}/explain`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ experiment_id: experimentId, provider }),
  });
  if (!res.ok) throw new Error(`Failed to generate explanation: ${res.statusText}`);
  return res.json();
}

export async function fetchValidationPoints(experimentId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/experiments/${experimentId}/validation-points`);
  if (!res.ok) throw new Error(`Failed to fetch validation points: ${res.statusText}`);
  return res.json();
}

export async function fetchCalibration(): Promise<any> {
  const res = await fetch(`${API_BASE}/calibration`);
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

