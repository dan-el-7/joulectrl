import React from 'react';
import { CapabilitiesResponse, WorkloadInfo, classCpus } from '../types';
import { colors } from '../design';
import { fetchSystemNoise, quietSystem, SystemNoiseStatus } from '../api';


/** Numeric text input synced with a slider — free typing, no artificial caps. */
const NumField: React.FC<{
  value: number;
  onCommit: (v: number) => void;
  min?: number;
  max?: number;
  unit?: string;
  width?: number;
}> = ({ value, onCommit, min = 0, max, unit, width = 84 }) => {
  const [text, setText] = React.useState(String(value));
  const [focused, setFocused] = React.useState(false);
  React.useEffect(() => {
    if (!focused) setText(String(value));
  }, [value, focused]);
  const commit = () => {
    const v = parseFloat(text);
    if (Number.isFinite(v) && v >= min && (max === undefined || v <= max)) onCommit(v);
    else setText(String(value));
  };
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
      <input
        type="text"
        inputMode="decimal"
        value={text}
        onFocus={() => setFocused(true)}
        onBlur={() => { setFocused(false); commit(); }}
        onKeyDown={(e) => { if (e.key === 'Enter') { commit(); (e.target as HTMLInputElement).blur(); } }}
        onChange={(e) => setText(e.target.value)}
        style={{
          width, padding: '2px 6px', borderRadius: 4,
          border: `1px solid ${colors.border}`, background: colors.surfaceElevated,
          color: colors.textPrimary, fontFamily: 'inherit', fontSize: '0.8rem',
        }}
      />
      {unit && <span style={{ fontSize: '0.72rem', color: colors.textTertiary }}>{unit}</span>}
    </span>
  );
};

/** Honest warning when a runtime budget is implausibly small/large vs the task. */
const budgetWarning = (budgetS: number | null, estTaskS?: number | null): string | null => {
  if (budgetS === null) return null;
  if (budgetS < 1) return 'Sub-second budget: almost no measured configuration can finish in time — the selector will honestly report no feasible point.';
  if (budgetS < 5) return 'Very tight budget: only the fastest (highest-power) configurations can meet this; expect little or no energy saving.';
  if (estTaskS && budgetS < estTaskS * 0.5)
    return `Budget is less than half the measured baseline runtime (~${estTaskS.toFixed(1)}s) — likely infeasible; the baseline itself may not finish in time.`;
  if (budgetS > 3600) return 'Budget over an hour: valid, but energy savings plateau once runtime is unconstrained.';
  return null;
};

interface SetupViewProps {
  capabilities: CapabilitiesResponse | null;
  workloads: WorkloadInfo[];
  selectedWorkload: string;
  onSelectWorkload: (id: string) => void;
  objective: string;
  onChangeObjective: (obj: string) => void;
  runtimeBudgetS: number | null;
  onChangeRuntimeBudget: (val: number | null) => void;
  energyTargetPct: number;
  onChangeEnergyTarget: (val: number) => void;
  perfFloorPct: number;
  onChangePerfFloor: (val: number) => void;
  calibrationBudgetS: number | null;
  onChangeCalibrationBudget: (val: number | null) => void;
  expPassiveCaps: boolean;
  onChangeExpPassiveCaps: (val: boolean) => void;
  repetitions?: number;
  onChangeRepetitions?: (val: number) => void;
  onStartExperiment: () => void;
  isStarting: boolean;
  baselineRuntimeS?: number | null;
  hasCalibration?: boolean;
  latestWatchedSegment?: {
    duration_s: number;
    suggested_budget_s: number;
  } | null;
  onOpenWatchTab?: () => void;
}

export const SetupView: React.FC<SetupViewProps> = ({
  capabilities,
  workloads,
  selectedWorkload,
  onSelectWorkload,
  objective,
  onChangeObjective,
  runtimeBudgetS,
  onChangeRuntimeBudget,
  energyTargetPct,
  onChangeEnergyTarget,
  perfFloorPct,
  onChangePerfFloor,
  calibrationBudgetS,
  onChangeCalibrationBudget,
  expPassiveCaps,
  onChangeExpPassiveCaps,
  repetitions = 1,
  onChangeRepetitions,
  onStartExperiment,
  isStarting,
  baselineRuntimeS,
  hasCalibration = true,
  latestWatchedSegment,
  onOpenWatchTab,
}) => {
  const [noiseStatus, setNoiseStatus] = React.useState<SystemNoiseStatus | null>(null);
  const [isQuieting, setIsQuieting] = React.useState<boolean>(false);
  const [quietSuccessMsg, setQuietSuccessMsg] = React.useState<string | null>(null);
  const [showNoiseModal, setShowNoiseModal] = React.useState<boolean>(false);
  const [selectedAppsToQuiet, setSelectedAppsToQuiet] = React.useState<Record<string, boolean>>({});

  const refreshNoise = React.useCallback(async () => {
    try {
      const st = await fetchSystemNoise();
      setNoiseStatus(st);
      const appSelection: Record<string, boolean> = {};
      st.detected_apps.forEach((a) => {
        appSelection[a.key] = true;
      });
      setSelectedAppsToQuiet(appSelection);
    } catch (e) {
      console.warn('Failed to fetch system noise', e);
    }
  }, []);

  React.useEffect(() => {
    refreshNoise();
    const interval = setInterval(refreshNoise, 8000);
    return () => clearInterval(interval);
  }, [refreshNoise]);

  const handleQuiet = async (appKeys?: string[]) => {
    setIsQuieting(true);
    try {
      const res = await quietSystem(appKeys);
      setNoiseStatus(res.remaining_noise);
      const closedNames = res.closed_apps.join(', ');
      setQuietSuccessMsg(closedNames ? `Closed ${closedNames}. Baseline quieted.` : 'Quiet baseline applied.');
      setTimeout(() => setQuietSuccessMsg(null), 5000);
    } catch (e) {
      console.error('Failed to quiet system', e);
    } finally {
      setIsQuieting(false);
    }
  };

  const handleStartWithCheck = () => {
    const isCalibratingOrSweeping =
      !hasCalibration || (calibrationBudgetS !== null && calibrationBudgetS > 0) || repetitions > 1;
    if (isCalibratingOrSweeping && noiseStatus && !noiseStatus.is_quiet) {
      setShowNoiseModal(true);
      return;
    }
    onStartExperiment();
  };
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: '1.5rem', maxWidth: '1100px', margin: '0 auto' }}>
      {/* Left Column: Workload & Objective Configuration */}
      <div style={{ background: colors.surface, borderRadius: '0.75rem', padding: '1.5rem', border: colors.border }}>
        <h2 style={{ margin: '0 0 1.25rem 0', fontSize: '1.15rem', color: colors.textPrimary, fontWeight: 600 }}>
          Experiment Setup
        </h2>

        {/* 1. Workload Selection */}
        <div style={{ marginBottom: '1.5rem' }}>
          <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: colors.textTertiary, marginBottom: '0.5rem' }}>
            Workload Plugin
          </label>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
            {workloads.map((w) => {
              const isSelected = w.id === selectedWorkload;
              return (
                <div
                  key={w.id}
                  onClick={() => onSelectWorkload(w.id)}
                  style={{
                    padding: '0.75rem',
                    borderRadius: '0.5rem',
                    border: `1.5px solid ${isSelected ? colors.accent : 'rgba(255,255,255,0.08)'}`,
                    backgroundColor: isSelected ? 'rgba(113,112,255,0.14)25' : colors.surfaceElevated,
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div style={{ fontWeight: 600, fontSize: '0.9rem', color: isSelected ? colors.accentHover : colors.textSecondary }}>
                    {w.name}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: colors.textTertiary, marginTop: '0.25rem' }}>
                    {w.description}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* 2. Objective Selection */}
        <div style={{ marginBottom: '1.5rem' }}>
          <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: colors.textTertiary, marginBottom: '0.5rem' }}>
            Optimization Objective
          </label>
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
            {[
              { id: 'deadline', label: 'Deadline Mode', desc: 'Finish within runtime budget' },
              { id: 'preference', label: 'Preference Mode', desc: '70% energy / 90% perf tradeoff' },
              { id: 'frontier', label: 'Explore Frontier', desc: 'View all Pareto candidates' },
            ].map((obj) => (
              <button
                key={obj.id}
                onClick={() => onChangeObjective(obj.id)}
                style={{
                  flex: 1,
                  padding: '0.5rem',
                  borderRadius: '0.375rem',
                  border: `1.5px solid ${objective === obj.id ? colors.emerald : 'rgba(255,255,255,0.08)'}`,
                  backgroundColor: objective === obj.id ? 'rgba(16,185,129,0.20)' : colors.surfaceElevated,
                  color: objective === obj.id ? colors.emerald : colors.textSecondary,
                  fontSize: '0.8rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  textAlign: 'center',
                }}
              >
                <div>{obj.label}</div>
              </button>
            ))}
          </div>

          {/* Conditional inputs based on Objective */}
          {objective === 'deadline' && (
            <div style={{ background: colors.surfaceElevated, padding: '1rem', borderRadius: '0.5rem', border: '1px solid rgba(255,255,255,0.08)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <span style={{ fontSize: '0.85rem', color: colors.textSecondary }}>Runtime Budget:</span>
                <span style={{ fontSize: '0.95rem', fontWeight: 700, color: colors.emerald }}>
                  {runtimeBudgetS === null ? 'Unlimited' : `${runtimeBudgetS}s`}
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <input
                  type="range"
                  min="1"
                  max="300"
                  step="0.5"
                  value={Math.min(Math.max(runtimeBudgetS ?? 45, 1), 300)}
                  disabled={runtimeBudgetS === null}
                  onChange={(e) => onChangeRuntimeBudget(parseFloat(e.target.value))}
                  style={{ flex: 1, accentColor: colors.emerald }}
                />
                <NumField
                  value={runtimeBudgetS ?? 45}
                  onCommit={onChangeRuntimeBudget}
                  unit="s"
                />
                <label style={{ fontSize: '0.75rem', color: colors.textTertiary, display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                  <input
                    type="checkbox"
                    checked={runtimeBudgetS === null}
                    onChange={(e) => onChangeRuntimeBudget(e.target.checked ? null : 45.0)}
                  />
                  Unlimited
                </label>
              </div>

              {/* Watch Mode Auto-detect helper */}
              {latestWatchedSegment ? (
                <div style={{ marginTop: '0.75rem', background: 'rgba(113,112,255,0.08)', border: '1px solid rgba(113,112,255,0.25)', borderRadius: '0.375rem', padding: '0.45rem 0.65rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.76rem', color: colors.textSecondary }}>
                    ⚡ Watched task: <strong>{latestWatchedSegment.duration_s}s</strong> (suggested: {latestWatchedSegment.suggested_budget_s}s)
                  </span>
                  <button
                    type="button"
                    onClick={() => onChangeRuntimeBudget(latestWatchedSegment.suggested_budget_s)}
                    style={{
                      padding: '0.2rem 0.55rem',
                      borderRadius: 4,
                      background: colors.accentBg,
                      color: colors.textPrimary,
                      border: 'none',
                      fontSize: '0.72rem',
                      cursor: 'pointer',
                      fontWeight: 600,
                    }}
                  >
                    Apply Watched
                  </button>
                </div>
              ) : (
                <div style={{ marginTop: '0.5rem', display: 'flex', justifyContent: 'flex-end' }}>
                  <button
                    type="button"
                    onClick={onOpenWatchTab}
                    style={{ background: 'transparent', border: 'none', color: colors.accentHover, fontSize: '0.74rem', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4 }}
                  >
                    <span>⏱ Auto-detect task runtime in Watch Mode →</span>
                  </button>
                </div>
              )}

              <div style={{ fontSize: '0.72rem', color: colors.textTertiary, marginTop: '0.4rem' }}>
                Rule: lowest-energy measured configuration meeting the empirical runtime rule (with 5% guard margin).
              </div>
              {budgetWarning(runtimeBudgetS, baselineRuntimeS) && (
                <div style={{ fontSize: '0.75rem', color: colors.amber, marginTop: '0.35rem', display: 'flex', gap: 6 }}>
                  <span>⚠</span>
                  <span>{budgetWarning(runtimeBudgetS, baselineRuntimeS)}</span>
                </div>
              )}
            </div>
          )}

          {objective === 'preference' && (
            <div style={{ background: colors.surfaceElevated, padding: '1rem', borderRadius: '0.5rem', border: '1px solid rgba(255,255,255,0.08)', display: 'flex', flexDirection: 'column', gap: '0.8rem' }}>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', color: colors.textSecondary, marginBottom: '0.3rem' }}>
                  <span>Energy Target:</span>
                  <span style={{ fontWeight: 700, color: colors.amber }}>≤ {energyTargetPct}% of baseline</span>
                </div>
                <input
                  type="range"
                  min="5"
                  max="100"
                  step="5"
                  value={Math.min(Math.max(energyTargetPct, 5), 100)}
                  onChange={(e) => onChangeEnergyTarget(parseInt(e.target.value))}
                  style={{ width: '100%', accentColor: colors.amber }}
                />
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 4 }}>
                  <NumField value={energyTargetPct} onCommit={onChangeEnergyTarget} unit="%" />
                </div>
              </div>

              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', color: colors.textSecondary, marginBottom: '0.3rem' }}>
                  <span>Performance Floor:</span>
                  <span style={{ fontWeight: 700, color: colors.accent }}>≥ {perfFloorPct}% baseline speed (runtime ≤ {Math.round(10000 / perfFloorPct)}%)</span>
                </div>
                <input
                  type="range"
                  min="10"
                  max="100"
                  step="5"
                  value={Math.min(Math.max(perfFloorPct, 10), 100)}
                  onChange={(e) => onChangePerfFloor(parseInt(e.target.value))}
                  style={{ width: '100%', accentColor: colors.accent }}
                />
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 4 }}>
                  <NumField value={perfFloorPct} onCommit={onChangePerfFloor} unit="%" />
                </div>
              </div>
              <div style={{ fontSize: '0.72rem', color: colors.textTertiary }}>
                Spec §6c: Reports closest honest outcome explicitly if no single candidate satisfies both constraints.
              </div>
            </div>
          )}
        </div>

        {/* Accuracy & Repeatability Control */}
        <div style={{ marginBottom: '1.5rem', background: colors.surfaceElevated, padding: '0.85rem 1rem', borderRadius: '0.5rem', border: '1px solid rgba(255,255,255,0.08)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: '0.85rem', fontWeight: 600, color: colors.textPrimary, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <span>🎯 Run Accuracy & Lineup</span>
              </div>
              <div style={{ fontSize: '0.74rem', color: colors.textTertiary, marginTop: '0.2rem' }}>
                Run each test configuration twice to verify consistency and ensure measurements line up.
              </div>
            </div>
            <div style={{ display: 'flex', gap: '0.4rem' }}>
              {[
                { val: 1, label: '1x (Single)' },
                { val: 2, label: '2x (Verify Lineup)' },
              ].map((opt) => (
                <button
                  key={opt.val}
                  type="button"
                  onClick={() => onChangeRepetitions && onChangeRepetitions(opt.val)}
                  style={{
                    padding: '0.35rem 0.75rem',
                    borderRadius: '0.375rem',
                    border: `1.5px solid ${repetitions === opt.val ? colors.accent : 'rgba(255,255,255,0.1)'}`,
                    backgroundColor: repetitions === opt.val ? 'rgba(113,112,255,0.22)' : colors.surface,
                    color: repetitions === opt.val ? colors.accentHover : colors.textSecondary,
                    fontSize: '0.78rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* System Noise & Background Activity Card */}
        <div
          style={{
            marginBottom: '1.5rem',
            background: noiseStatus?.is_quiet ? 'rgba(16,185,129,0.05)' : 'rgba(245,158,11,0.08)',
            border: `1px solid ${noiseStatus?.is_quiet ? 'rgba(16,185,129,0.22)' : 'rgba(245,158,11,0.28)'}`,
            borderRadius: '0.5rem',
            padding: '0.85rem 1rem',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ flex: 1, marginRight: '0.75rem' }}>
              <div
                style={{
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  color: colors.textPrimary,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                }}
              >
                <span>{noiseStatus?.is_quiet ? '✓ System Baseline Quiet' : '⚠️ Background Noise Detected'}</span>
              </div>
              <div style={{ fontSize: '0.74rem', color: colors.textTertiary, marginTop: '0.2rem', lineHeight: '1.35' }}>
                {noiseStatus?.is_quiet
                  ? 'No extra background applications detected. Clean baseline for calibration & sweep accuracy.'
                  : `${noiseStatus?.detected_apps.map((a) => a.name).join(', ')} active (${noiseStatus?.total_noise_cpu_pct}% CPU). Extra background load can skew silicon power curves.`}
              </div>
            </div>
            {!noiseStatus?.is_quiet && (
              <button
                type="button"
                disabled={isQuieting}
                onClick={() => handleQuiet()}
                style={{
                  padding: '0.35rem 0.75rem',
                  borderRadius: '0.375rem',
                  backgroundColor: 'rgba(245,158,11,0.18)',
                  border: '1px solid rgba(245,158,11,0.4)',
                  color: '#f59e0b',
                  fontSize: '0.78rem',
                  fontWeight: 600,
                  cursor: isQuieting ? 'wait' : 'pointer',
                  whiteSpace: 'nowrap',
                  transition: 'all 0.15s ease',
                }}
              >
                {isQuieting ? 'Quieting...' : '🧹 Close Extra Apps'}
              </button>
            )}
          </div>
          {quietSuccessMsg && (
            <div style={{ marginTop: '0.45rem', fontSize: '0.75rem', color: colors.emerald, fontWeight: 500 }}>
              ✓ {quietSuccessMsg}
            </div>
          )}
        </div>

        {/* 3. Calibration Sweep & Scan Duration */}
        <div
          style={{
            marginBottom: '1.5rem',
            background: colors.surfaceElevated,
            border: `1px solid ${hasCalibration ? 'rgba(16,185,129,0.22)' : colors.border}`,
            borderRadius: '0.5rem',
            padding: '1rem',
          }}
        >
          {/* Header & Status */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem' }}>
            <div>
              <div style={{ fontSize: '0.85rem', fontWeight: 600, color: colors.textPrimary, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <span>⏱️ Calibration Sweep Budget (Scan Duration)</span>
              </div>
              <div style={{ fontSize: '0.74rem', color: colors.textTertiary, marginTop: '0.2rem' }}>
                {hasCalibration
                  ? 'Use pre-measured verified calibration data (instant 0s) or run a live sweep to measure configurations for this workload.'
                  : 'No existing calibration found — a live hardware sweep is required before optimization.'}
              </div>
            </div>

            {hasCalibration ? (
              <span
                style={{
                  background: 'rgba(16,185,129,0.12)',
                  color: colors.emerald,
                  fontSize: '0.7rem',
                  fontWeight: 600,
                  padding: '0.2rem 0.5rem',
                  borderRadius: '0.25rem',
                  border: '1px solid rgba(16,185,129,0.3)',
                  whiteSpace: 'nowrap',
                }}
              >
                ✓ Verified Curves Loaded
              </span>
            ) : (
              <span
                style={{
                  background: 'rgba(245,158,11,0.12)',
                  color: colors.amber,
                  fontSize: '0.7rem',
                  fontWeight: 600,
                  padding: '0.2rem 0.5rem',
                  borderRadius: '0.25rem',
                  border: '1px solid rgba(245,158,11,0.3)',
                  whiteSpace: 'nowrap',
                }}
              >
                ⚠️ Sweep Required
              </span>
            )}
          </div>

          {/* Quick Presets */}
          <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap', marginBottom: '0.85rem' }}>
            {hasCalibration && (
              <button
                type="button"
                onClick={() => onChangeCalibrationBudget(0)}
                style={{
                  padding: '0.35rem 0.65rem',
                  borderRadius: '0.375rem',
                  border: `1.5px solid ${calibrationBudgetS === 0 ? colors.emerald : 'rgba(255,255,255,0.1)'}`,
                  backgroundColor: calibrationBudgetS === 0 ? 'rgba(16,185,129,0.15)' : colors.surface,
                  color: calibrationBudgetS === 0 ? colors.emerald : colors.textSecondary,
                  fontSize: '0.76rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                ⚡ 0s (Instant)
              </button>
            )}

            {[
              { val: 60, label: '60s (Quick)' },
              { val: 120, label: '120s (Standard)' },
              { val: 300, label: '300s (Thorough)' },
              { val: 600, label: '600s (Deep)' },
            ].map((preset) => {
              const isSelected = calibrationBudgetS === preset.val;
              return (
                <button
                  key={preset.val}
                  type="button"
                  onClick={() => onChangeCalibrationBudget(preset.val)}
                  style={{
                    padding: '0.35rem 0.65rem',
                    borderRadius: '0.375rem',
                    border: `1.5px solid ${isSelected ? colors.accent : 'rgba(255,255,255,0.1)'}`,
                    backgroundColor: isSelected ? 'rgba(113,112,255,0.22)' : colors.surface,
                    color: isSelected ? colors.accentHover : colors.textSecondary,
                    fontSize: '0.76rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  {preset.label}
                </button>
              );
            })}

            <button
              type="button"
              onClick={() => onChangeCalibrationBudget(calibrationBudgetS === null ? 120 : null)}
              style={{
                padding: '0.35rem 0.65rem',
                borderRadius: '0.375rem',
                border: `1.5px solid ${calibrationBudgetS === null ? colors.accent : 'rgba(255,255,255,0.1)'}`,
                backgroundColor: calibrationBudgetS === null ? 'rgba(113,112,255,0.22)' : colors.surface,
                color: calibrationBudgetS === null ? colors.accentHover : colors.textSecondary,
                fontSize: '0.76rem',
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              ♾️ Exhaustive
            </button>
          </div>

          {/* Slider + NumField */}
          <div style={{ background: colors.surface, padding: '0.75rem', borderRadius: '0.375rem', border: '1px solid rgba(255,255,255,0.06)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: colors.textTertiary, marginBottom: '0.4rem' }}>
              <span>Sweep Duration:</span>
              <span style={{ color: colors.textSecondary, fontWeight: 600 }}>
                {calibrationBudgetS === null
                  ? 'Exhaustive (~1800s safety limit)'
                  : calibrationBudgetS === 0
                    ? '0s (Instant · Pre-measured Calibration)'
                    : `${calibrationBudgetS}s (~${(calibrationBudgetS / 60).toFixed(1)} min)`}
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <input
                type="range"
                min="30"
                max="1800"
                step="10"
                value={
                  calibrationBudgetS === null
                    ? 1800
                    : calibrationBudgetS === 0
                      ? 120
                      : Math.min(Math.max(calibrationBudgetS, 30), 1800)
                }
                disabled={calibrationBudgetS === null}
                onChange={(e) => onChangeCalibrationBudget(parseInt(e.target.value, 10))}
                style={{
                  flex: 1,
                  accentColor: colors.accent,
                  opacity: calibrationBudgetS === 0 ? 0.5 : 1,
                }}
              />
              <NumField
                value={calibrationBudgetS === null ? 0 : calibrationBudgetS}
                onCommit={(v) => onChangeCalibrationBudget(v)}
                min={0}
                max={3600}
                unit="s"
              />
              <label style={{ fontSize: '0.72rem', color: colors.textTertiary, display: 'flex', alignItems: 'center', gap: '0.3rem', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={calibrationBudgetS === null}
                  onChange={(e) => onChangeCalibrationBudget(e.target.checked ? null : 120)}
                />
                Exhaustive
              </label>
            </div>

            {/* Explanation & Point Estimate */}
            <div style={{ marginTop: '0.5rem', fontSize: '0.73rem', color: colors.textTertiary, lineHeight: '1.4' }}>
              {calibrationBudgetS === 0 ? (
                <span style={{ color: colors.emerald }}>
                  ✓ Instant mode: Starts optimization immediately using existing verified hardware curves and baseline (0s scan). Select 60s, 120s, or 600s above to run a fresh live sweep.
                </span>
              ) : calibrationBudgetS === null ? (
                <span style={{ color: colors.textSecondary }}>
                  ♾️ Exhaustive mode: Sweeps all valid frequency and core configurations until complete (bounded by ~1800s safety limit).
                </span>
              ) : (
                <span style={{ color: colors.textSecondary }}>
                  ⏱️ Live sweep will measure ~
                  <strong style={{ color: colors.accentHover }}>
                    {Math.max(1, Math.floor(calibrationBudgetS / (repetitions > 1 ? 12 : 6)))}
                  </strong>{' '}
                  points across core classes ({repetitions > 1 ? '2 runs per point for verified lineup' : '1 run per point'}). Ordered via bisection (peak, base, quartiles) for an accurate representative curve.
                </span>
              )}
            </div>
          </div>

          {/* Experimental passive caps */}
          <div style={{ marginTop: '0.75rem' }}>
            <label style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={expPassiveCaps}
                onChange={(e) => onChangeExpPassiveCaps(e.target.checked)}
                style={{ marginTop: 2, accentColor: colors.amber }}
              />
              <span style={{ fontSize: '0.75rem', color: colors.textTertiary }}>
                <span style={{ color: colors.amber, fontWeight: 600 }}>Experimental:</span> passive-mode caps (sweeps 2.5–4.5 GHz boost-on points)
              </span>
            </label>
          </div>
        </div>

        {/* Action Button */}
        <button
          onClick={handleStartWithCheck}
          disabled={isStarting}
          style={{
            width: '100%',
            padding: '0.75rem',
            borderRadius: '0.5rem',
            backgroundColor: colors.accentBg,
            color: colors.textPrimary,
            fontSize: '0.95rem',
            fontWeight: 600,
            border: 'none',
            cursor: isStarting ? 'wait' : 'pointer',
            boxShadow: '0 4px 6px -1px rgba(37, 99, 235, 0.3)',
          }}
        >
          {isStarting
            ? 'Optimizing Workload...'
            : calibrationBudgetS && calibrationBudgetS > 0
              ? `Run ${calibrationBudgetS}s Sweep & Optimize Workload`
              : calibrationBudgetS === null
                ? 'Run Exhaustive Sweep & Optimize Workload'
                : objective === 'deadline'
                  ? 'Optimize Workload for Deadline (Instant)'
                  : objective === 'preference'
                    ? 'Optimize for Preference Target (Instant)'
                    : 'Explore Pareto Candidates (Instant)'}
        </button>
      </div>

      {/* Right Column: Hardware Discovery Card */}
      <div style={{ background: colors.surface, borderRadius: '0.75rem', padding: '1.5rem', border: colors.border }}>
        <h2 style={{ margin: '0 0 1.25rem 0', fontSize: '1.15rem', color: colors.textPrimary, fontWeight: 600 }}>
          Hardware Discovery & Capabilities
        </h2>

        {capabilities ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', fontSize: '0.85rem' }}>
            {/* data provenance — never present fixture data as this machine */}
            {capabilities.source === 'fixture' && (
              <div
                style={{
                  background: 'rgba(245,158,11,0.10)',
                  border: `1px solid ${colors.amber}`,
                  borderRadius: '0.5rem',
                  padding: '0.6rem 0.75rem',
                  fontSize: '0.78rem',
                  color: colors.amber,
                }}
              >
                <strong>Demo-laptop fixture data — not discovered on this machine.</strong>{' '}
                {capabilities.note ??
                  'Live hardware discovery is unavailable here (needs Linux sysfs); the values below come from the committed reference fixture.'}
              </div>
            )}
            {capabilities.source === 'live' && (
              <div
                style={{
                  background: 'rgba(16,185,129,0.10)',
                  border: `1px solid ${colors.emerald}`,
                  borderRadius: '0.5rem',
                  padding: '0.6rem 0.75rem',
                  fontSize: '0.78rem',
                  color: colors.emerald,
                }}
              >
                <strong>Live discovery</strong> — hardware read from this machine.
              </div>
            )}
            <div style={{ background: colors.surfaceElevated, padding: '0.75rem', borderRadius: '0.5rem', border: '1px solid rgba(255,255,255,0.08)' }}>
              <div style={{ color: colors.textTertiary, fontSize: '0.75rem' }}>Processor / Topology</div>
              <div style={{ fontWeight: 600, color: colors.textPrimary, marginTop: '0.2rem' }}>
                {capabilities.machine.cpu_model}
              </div>
              <div style={{ color: colors.textTertiary, marginTop: '0.2rem', fontSize: '0.75rem' }}>
                {capabilities.topology.logical_cores} logical CPUs ({capabilities.topology.physical_cores} physical cores)
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem', flexWrap: 'wrap' }}>
                {Object.entries(capabilities.topology.classes ?? {}).map(([cls, cpus]) => (
                  <span
                    key={cls}
                    style={{
                      background: cls === 'fast' ? 'rgba(16,185,129,0.12)' : 'rgba(245,158,11,0.10)',
                      color: cls === 'fast' ? colors.emerald : colors.amber,
                      padding: '0.15rem 0.4rem',
                      borderRadius: '0.25rem',
                      fontSize: '0.7rem',
                    }}
                  >
                    {cls} class: CPUs {classCpus(cpus).join(', ')}
                  </span>
                ))}
              </div>
            </div>

            {/* Checklist of Gates */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>Package-energy access (RAPL)</span>
                <span style={{ color: colors.emerald, fontWeight: 700 }}>✓ Verified ({capabilities.energy.idle_watts} W idle)</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>CPU Frequency Caps</span>
                <span style={{ color: colors.emerald, fontWeight: 700 }}>✓ Verified (16 policies, boost=0 pair)</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>Global Boost Toggle</span>
                <span style={{ color: colors.emerald, fontWeight: 700 }}>✓ Verified</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>Restoration Engine</span>
                <span style={{ color: colors.emerald, fontWeight: 700 }}>✓ Available</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>Tuned PM Profile</span>
                <span style={{ color: colors.accentHover, fontWeight: 600 }}>{capabilities.machine.tuned_active_profile}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>AC Power Supply</span>
                <span style={{ color: capabilities.machine.ac_power ? colors.emerald : colors.amber, fontWeight: 600 }}>
                  {capabilities.machine.ac_power ? '✓ Connected' : '⚠ On Battery'}
                </span>
              </div>
            </div>

            <div style={{ background: colors.surfaceElevated, border: colors.border, borderRadius: '0.5rem', padding: '0.6rem', fontSize: '0.72rem', color: colors.textTertiary }}>
              <strong>Non-negotiable rule:</strong> Package energy measured directly from verified hardware counter. Missing energy is never relabeled as zero.
            </div>
          </div>
        ) : (
          <div style={{ color: colors.textTertiary }}>Loading machine capabilities...</div>
        )}
      </div>

      {/* Pre-Calibration / Sweep Background Noise Modal */}
      {showNoiseModal && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.78)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            backdropFilter: 'blur(4px)',
          }}
        >
          <div
            style={{
              background: colors.surface,
              border: '1px solid rgba(255,255,255,0.15)',
              borderRadius: '0.75rem',
              padding: '1.5rem',
              maxWidth: '500px',
              width: '90%',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.6)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.85rem' }}>
              <span style={{ fontSize: '1.4rem' }}>🧹</span>
              <h3 style={{ margin: 0, fontSize: '1.1rem', color: colors.textPrimary, fontWeight: 600 }}>
                Quiet Background Apps Before Calibrating?
              </h3>
            </div>
            <p style={{ fontSize: '0.84rem', color: colors.textSecondary, lineHeight: '1.45', marginBottom: '1rem' }}>
              You are about to run a hardware silicon sweep. Active background applications introduce CPU contention and thermal throttling, which can distort your energy and runtime curve.
            </p>

            <div
              style={{
                marginBottom: '1.25rem',
                background: colors.surfaceElevated,
                borderRadius: '0.5rem',
                padding: '0.75rem',
                border: '1px solid rgba(255,255,255,0.06)',
                maxHeight: '180px',
                overflowY: 'auto',
              }}
            >
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: colors.textTertiary, marginBottom: '0.4rem' }}>
                DETECTED BACKGROUND APPS:
              </div>
              {noiseStatus?.detected_apps.map((app) => (
                <label
                  key={app.key}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '0.35rem 0',
                    fontSize: '0.82rem',
                    color: colors.textPrimary,
                    cursor: 'pointer',
                  }}
                >
                  <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <input
                      type="checkbox"
                      checked={selectedAppsToQuiet[app.key] ?? true}
                      onChange={(e) => setSelectedAppsToQuiet({ ...selectedAppsToQuiet, [app.key]: e.target.checked })}
                      style={{ accentColor: colors.accent }}
                    />
                    <span>{app.name}</span>
                    <span style={{ fontSize: '0.72rem', color: colors.textTertiary }}>({app.process_count} procs)</span>
                  </span>
                  <span style={{ fontSize: '0.75rem', color: '#f59e0b', fontWeight: 500 }}>
                    {app.total_cpu_pct}% CPU · {app.total_mem_pct}% RAM
                  </span>
                </label>
              ))}
              {(noiseStatus?.unclassified_processes?.length ?? 0) > 0 && (
                <div
                  style={{
                    fontSize: '0.75rem',
                    color: colors.textTertiary,
                    marginTop: '0.4rem',
                    borderTop: '1px solid rgba(255,255,255,0.06)',
                    paddingTop: '0.4rem',
                  }}
                >
                  +{noiseStatus?.unclassified_processes.length} other background high-CPU process(es)
                </div>
              )}
            </div>

            <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
              <button
                type="button"
                onClick={() => setShowNoiseModal(false)}
                style={{
                  padding: '0.45rem 0.8rem',
                  borderRadius: '0.375rem',
                  background: 'transparent',
                  border: '1px solid rgba(255,255,255,0.15)',
                  color: colors.textSecondary,
                  fontSize: '0.82rem',
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowNoiseModal(false);
                  onStartExperiment();
                }}
                style={{
                  padding: '0.45rem 0.8rem',
                  borderRadius: '0.375rem',
                  background: colors.surfaceElevated,
                  border: '1px solid rgba(255,255,255,0.15)',
                  color: colors.textPrimary,
                  fontSize: '0.82rem',
                  cursor: 'pointer',
                }}
              >
                Start Without Closing
              </button>
              <button
                type="button"
                disabled={isQuieting}
                onClick={async () => {
                  const keysToQuiet = Object.entries(selectedAppsToQuiet)
                    .filter(([_, sel]) => sel)
                    .map(([k]) => k);
                  await handleQuiet(keysToQuiet.length > 0 ? keysToQuiet : undefined);
                  setShowNoiseModal(false);
                  onStartExperiment();
                }}
                style={{
                  padding: '0.45rem 0.95rem',
                  borderRadius: '0.375rem',
                  background: colors.accentBg,
                  border: 'none',
                  color: '#fff',
                  fontWeight: 600,
                  fontSize: '0.82rem',
                  cursor: isQuieting ? 'wait' : 'pointer',
                }}
              >
                {isQuieting ? 'Closing Apps...' : '🧹 Close Apps & Calibrate'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
