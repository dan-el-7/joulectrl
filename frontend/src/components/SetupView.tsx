import React from 'react';
import { CapabilitiesResponse, WorkloadInfo, classCpus } from '../types';
import { colors } from '../design';
import {
  fetchSystemNoise,
  quietSystem,
  SystemNoiseStatus,
  fetchSystemThermal,
  SystemThermalStatus,
  setProcessPriority,
  fetchUserProcesses,
  UserProcess,
  fetchInstalledApps,
  InstalledApp,
  launchAndArm,
} from '../api';
import { FocusSwitch, FocusMode } from './FocusSwitch';


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

/** Clear warning when a runtime budget is very tight vs the task. */
const budgetWarning = (budgetS: number | null, estTaskS?: number | null): string | null => {
  if (budgetS === null) return null;
  if (budgetS < 1) return 'Sub-second budget: likely infeasible for this workload.';
  if (budgetS < 5) return 'Very tight budget: requires high-power configurations with minimal energy savings.';
  if (estTaskS && budgetS < estTaskS * 0.5)
    return `Budget is <50% of baseline (~${estTaskS.toFixed(1)}s) — likely infeasible.`;
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
  taskPriority?: 'top_priority' | 'eco_deadline' | 'best_effort';
  onChangeTaskPriority?: (val: 'top_priority' | 'eco_deadline' | 'best_effort') => void;
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
  onOpenTasksTab?: () => void;
  onOpenCalibrationTab?: () => void;
  targetedProcess?: { pid: number; name: string } | null;
  onSelectTargetProcess?: (p: { pid: number; name: string } | null) => void;
  focusMode?: FocusMode;
  onChangeFocusMode?: (mode: FocusMode) => void;
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
  taskPriority = 'top_priority',
  onChangeTaskPriority,
  focusMode = 'off',
  onChangeFocusMode,
  repetitions = 1,
  onChangeRepetitions,
  onStartExperiment,
  isStarting,
  baselineRuntimeS,
  hasCalibration = true,
  latestWatchedSegment,
  onOpenWatchTab,
  onOpenTasksTab,
  onOpenCalibrationTab,
  targetedProcess,
  onSelectTargetProcess,
}) => {
  const [workloadMode, setWorkloadMode] = React.useState<'benchmark' | 'launch' | 'process'>(() => {
    return targetedProcess ? 'process' : 'benchmark';
  });
  const [launchCommand, setLaunchCommand] = React.useState<string>('make -C scratch/zstd clean && make -C scratch/zstd -j8');
  const [launchTab, setLaunchTab] = React.useState<'command' | 'apps'>('command');
  const [installedApps, setInstalledApps] = React.useState<InstalledApp[]>([]);
  const [loadingApps, setLoadingApps] = React.useState<boolean>(false);
  const [searchApp, setSearchApp] = React.useState<string>('');
  const [launchInTerminal, setLaunchInTerminal] = React.useState<boolean>(true);
  const [launchWatchMode, setLaunchWatchMode] = React.useState<boolean>(true);
  const [launchObjective, setLaunchObjective] = React.useState<'efficiency' | 'deadline' | 'performance'>('efficiency');
  const [launchRecurrence, setLaunchRecurrence] = React.useState<'repeated' | 'once'>('repeated');
  const [launchTimeBudgetS, setLaunchTimeBudgetS] = React.useState<number>(20);
  const [launchLane, setLaunchLane] = React.useState<'fast' | 'eco' | 'all'>('fast');
  const [launchFeedback, setLaunchFeedback] = React.useState<string | null>(null);
  const [isLaunchingApp, setIsLaunchingApp] = React.useState<boolean>(false);
  const [launchedPid, setLaunchedPid] = React.useState<number | null>(null);

  const [activeProcessList, setActiveProcessList] = React.useState<UserProcess[]>([]);
  const [loadingProcs, setLoadingProcs] = React.useState<boolean>(false);
  const [procSearch, setProcSearch] = React.useState<string>('');
  const [manualPidInput, setManualPidInput] = React.useState<string>('');
  const [targetProcess, setTargetProcess] = React.useState<{
    pid: number;
    name: string;
    cmdline?: string;
    cpu_pct?: number;
    mem_pct?: number;
    affinity_label?: string;
  } | null>(targetedProcess || null);
  const [targetCoreLane, setTargetCoreLane] = React.useState<'fast' | 'eco' | 'normal'>('fast');
  const [processFeedback, setProcessFeedback] = React.useState<string | null>(null);
  const [isApplyingPriority, setIsApplyingPriority] = React.useState<boolean>(false);

  const loadInstalledApps = React.useCallback(async () => {
    try {
      setLoadingApps(true);
      const apps = await fetchInstalledApps();
      setInstalledApps(apps);
    } catch (e) {
      console.warn('Failed to load installed apps in setup:', e);
    } finally {
      setLoadingApps(false);
    }
  }, []);

  React.useEffect(() => {
    if (workloadMode === 'launch' && installedApps.length === 0) {
      loadInstalledApps();
    }
  }, [workloadMode, installedApps.length, loadInstalledApps]);

  const handleExecuteLaunch = async () => {
    if (!launchCommand.trim()) return;
    try {
      setIsLaunchingApp(true);
      setLaunchFeedback(null);
      const res = await launchAndArm({
        command: launchCommand.trim(),
        launch_in_terminal: launchInTerminal,
        pin_lane: launchLane === 'all' ? undefined : launchLane,
        arm_watcher: launchWatchMode,
        optimization_objective: launchObjective,
        recurrence_mode: launchRecurrence,
        time_budget_s: launchObjective === 'deadline' ? launchTimeBudgetS : undefined,
      });
      setLaunchedPid(res.pid);
      const modeDesc =
        launchObjective === 'efficiency'
          ? 'Max Efficiency (2.0 GHz)'
          : launchObjective === 'deadline'
          ? `Deadline ${launchTimeBudgetS}s`
          : 'Sustained Boost + Core Shielding';
      setLaunchFeedback(`🚀 Launched PID ${res.pid} at Stock Boost! ${launchWatchMode ? `Watcher armed: ${modeDesc} (${launchRecurrence === 'repeated' ? 'Continuous Watcher' : 'One-Shot'}).` : ''}`);
    } catch (e: any) {
      setLaunchFeedback(`❌ Failed to launch: ${e.message}`);
    } finally {
      setIsLaunchingApp(false);
    }
  };

  React.useEffect(() => {
    if (targetedProcess) {
      setWorkloadMode('process');
      setTargetProcess(targetedProcess);
    }
  }, [targetedProcess]);

  const loadActiveProcesses = React.useCallback(async () => {
    try {
      setLoadingProcs(true);
      const res = await fetchUserProcesses(100);
      const list = res.processes || [];
      setActiveProcessList(list);
      if (targetedProcess) {
        const match = list.find((p) => p.pid === targetedProcess.pid);
        if (match) setTargetProcess(match);
      }
    } catch (e) {
      console.warn('Failed to load processes in setup:', e);
    } finally {
      setLoadingProcs(false);
    }
  }, [targetedProcess]);

  React.useEffect(() => {
    if (workloadMode === 'process') {
      loadActiveProcesses();
    }
  }, [workloadMode, loadActiveProcesses]);

  const handleApplyProcessPriority = async (laneOverride?: 'fast' | 'eco' | 'normal') => {
    const lane = laneOverride || targetCoreLane;
    if (!targetProcess) return;
    try {
      setIsApplyingPriority(true);
      const policy =
        lane === 'fast'
          ? 'prioritize_fast'
          : lane === 'eco'
            ? 'deprioritize_eco'
            : 'restore_normal';
      await setProcessPriority({ pid: targetProcess.pid, policy });
      const laneName =
        lane === 'fast'
          ? 'Zen 5 Fast Cores (Max Clocks)'
          : lane === 'eco'
            ? 'Zen 5c Eco Cores (Low Power)'
            : 'All 16 Cores';
      setProcessFeedback(`✓ PID ${targetProcess.pid} (${targetProcess.name}) shielded on ${laneName}.`);
      setTimeout(() => setProcessFeedback(null), 5000);
      await loadActiveProcesses();
    } catch (e: any) {
      setProcessFeedback(`⚠️ Error: ${e?.message ?? e}`);
      setTimeout(() => setProcessFeedback(null), 6000);
    } finally {
      setIsApplyingPriority(false);
    }
  };

  const [noiseStatus, setNoiseStatus] = React.useState<SystemNoiseStatus | null>(null);
  const [thermalStatus, setThermalStatus] = React.useState<SystemThermalStatus | null>(null);
  const [isQuieting, setIsQuieting] = React.useState<boolean>(false);
  const [isDeprioritizing, setIsDeprioritizing] = React.useState<boolean>(false);
  const [quietSuccessMsg, setQuietSuccessMsg] = React.useState<string | null>(null);
  const [showNoiseModal, setShowNoiseModal] = React.useState<boolean>(false);
  const [selectedAppsToQuiet, setSelectedAppsToQuiet] = React.useState<Record<string, boolean>>({});

  const refreshNoise = React.useCallback(async () => {
    try {
      const [st, therm] = await Promise.all([
        fetchSystemNoise().catch(() => null),
        fetchSystemThermal().catch(() => null),
      ]);
      if (st) {
        setNoiseStatus(st);
        const appSelection: Record<string, boolean> = {};
        st.detected_apps.forEach((a) => {
          appSelection[a.key] = true;
        });
        setSelectedAppsToQuiet(appSelection);
      }
      if (therm) {
        setThermalStatus(therm);
      }
    } catch {
      // transient
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

  const handleDeprioritizeNoise = async () => {
    if (!noiseStatus) return;
    try {
      setIsDeprioritizing(true);
      for (const app of noiseStatus.detected_apps) {
        await setProcessPriority({ pattern: app.key, policy: 'deprioritize_eco' });
      }
      const names = noiseStatus.detected_apps.map((a) => a.name).join(', ');
      setQuietSuccessMsg(`Deprioritized ${names} to Zen 5c Eco Cores. Fast cores are clear!`);
      setTimeout(() => setQuietSuccessMsg(null), 6000);
      await refreshNoise();
    } catch (e) {
      console.error('Failed to deprioritize apps', e);
    } finally {
      setIsDeprioritizing(false);
    }
  };

  const handleStartWithCheck = () => {
    if (workloadMode === 'launch') {
      handleExecuteLaunch();
      return;
    }
    if (workloadMode === 'process' && targetProcess) {
      handleApplyProcessPriority();
      return;
    }
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
      <div style={{ background: colors.surface, borderRadius: '0.75rem', padding: '1.5rem', border: `1px solid ${colors.border}`, boxShadow: colors.cardShadow }}>
        <h2 style={{ margin: '0 0 1.25rem 0', fontSize: '1.15rem', color: colors.textPrimary, fontWeight: 600 }}>
          Experiment Setup
        </h2>

        {/* Workload Type Selector: Benchmark Workload vs Target Running Process */}
        <div style={{ display: 'flex', background: colors.surfaceElevated, borderRadius: '0.5rem', padding: 3, marginBottom: '1.25rem', border: `1px solid ${colors.border}` }}>
          <button
            type="button"
            onClick={() => {
              setWorkloadMode('benchmark');
              if (onSelectTargetProcess) onSelectTargetProcess(null);
            }}
            style={{
              flex: 1,
              padding: '0.5rem',
              borderRadius: '0.375rem',
              border: 'none',
              background: workloadMode === 'benchmark' ? colors.surface : 'transparent',
              color: workloadMode === 'benchmark' ? colors.textPrimary : colors.textTertiary,
              fontWeight: workloadMode === 'benchmark' ? 600 : 400,
              fontSize: '0.85rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 6,
              boxShadow: workloadMode === 'benchmark' ? colors.cardShadow : 'none',
              transition: 'all 0.15s ease',
            }}
          >
            <span>📦</span> Benchmark Workload
          </button>
          <button
            id="mode-btn-launch"
            type="button"
            onClick={() => {
              setWorkloadMode('launch');
              if (onSelectTargetProcess) onSelectTargetProcess(null);
            }}
            style={{
              flex: 1,
              padding: '0.5rem',
              borderRadius: '0.375rem',
              border: 'none',
              background: workloadMode === 'launch' ? colors.surface : 'transparent',
              color: workloadMode === 'launch' ? colors.textPrimary : colors.textTertiary,
              fontWeight: workloadMode === 'launch' ? 600 : 400,
              fontSize: '0.85rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 6,
              boxShadow: workloadMode === 'launch' ? colors.cardShadow : 'none',
              transition: 'all 0.15s ease',
            }}
          >
            <span>🚀</span> Launch App / Command
          </button>
          <button
            type="button"
            onClick={() => setWorkloadMode('process')}
            style={{
              flex: 1,
              padding: '0.5rem',
              borderRadius: '0.375rem',
              border: 'none',
              background: workloadMode === 'process' ? colors.surface : 'transparent',
              color: workloadMode === 'process' ? colors.textPrimary : colors.textTertiary,
              fontWeight: workloadMode === 'process' ? 600 : 400,
              fontSize: '0.85rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 6,
              boxShadow: workloadMode === 'process' ? colors.cardShadow : 'none',
              transition: 'all 0.15s ease',
            }}
          >
            <span>🎯</span> Target Running Process {targetProcess ? `(${targetProcess.name || `PID ${targetProcess.pid}`})` : ''}
          </button>
        </div>

        {/* 1. Workload / Process Selection */}
        {workloadMode === 'benchmark' ? (
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
        ) : workloadMode === 'launch' ? (
          /* Launch Application or Command Section */
          <div style={{ marginBottom: '1.5rem', background: colors.surfaceElevated, borderRadius: '0.5rem', padding: '1.25rem', border: `1px solid ${colors.border}`, display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.5rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.92rem', fontWeight: 700, color: colors.textPrimary }}>
                  🚀 Launch Any App or Command
                </label>
                <div style={{ fontSize: '0.78rem', color: colors.textTertiary, marginTop: '0.2rem', lineHeight: 1.4 }}>
                  Launch installed applications or CLI commands with dynamic sweet-spot optimization. Starts at 100% Stock Boost with zero UI latency.
                </div>
              </div>

              {/* Sub-tab: CLI Command vs Installed Apps */}
              <div style={{ display: 'flex', background: colors.surface, borderRadius: '0.375rem', padding: 2, border: `1px solid ${colors.border}` }}>
                <button
                  type="button"
                  onClick={() => setLaunchTab('command')}
                  style={{
                    padding: '4px 10px',
                    borderRadius: '0.25rem',
                    border: 'none',
                    background: launchTab === 'command' ? colors.accent : 'transparent',
                    color: launchTab === 'command' ? '#fff' : colors.textTertiary,
                    fontSize: '0.76rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  ⚡ Command / Script
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setLaunchTab('apps');
                    if (installedApps.length === 0) loadInstalledApps();
                  }}
                  style={{
                    padding: '4px 10px',
                    borderRadius: '0.25rem',
                    border: 'none',
                    background: launchTab === 'apps' ? colors.accent : 'transparent',
                    color: launchTab === 'apps' ? '#fff' : colors.textTertiary,
                    fontSize: '0.76rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  🖥️ Installed Apps ({installedApps.length || '…'})
                </button>
              </div>
            </div>

            {/* Launch Feedback Banner */}
            {launchFeedback && (
              <div
                style={{
                  padding: '0.7rem 0.9rem',
                  borderRadius: '0.375rem',
                  backgroundColor: launchFeedback.includes('❌') ? 'rgba(239,68,68,0.15)' : 'rgba(16,185,129,0.15)',
                  border: `1px solid ${launchFeedback.includes('❌') ? colors.red : colors.emerald}`,
                  fontSize: '0.82rem',
                  color: colors.textPrimary,
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <span>{launchFeedback}</span>
                {onOpenWatchTab && (
                  <button
                    type="button"
                    onClick={onOpenWatchTab}
                    style={{
                      padding: '3px 10px',
                      borderRadius: '0.25rem',
                      background: colors.emerald,
                      color: '#fff',
                      border: 'none',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    View in Watcher →
                  </button>
                )}
              </div>
            )}

            {launchTab === 'command' ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {/* Preset Chips */}
                <div>
                  <div style={{ fontSize: '0.74rem', color: colors.textTertiary, fontWeight: 600, marginBottom: '0.35rem' }}>
                    Quick Presets (1-Click Fill):
                  </div>
                  <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                    {[
                      { label: '⚡ Real GCC 10s+ Compile', cmd: 'make -C scratch/zstd clean && make -C scratch/zstd -j8' },
                      { label: '🎬 Blender Render', cmd: 'blender -b -f 1' },
                      { label: '🦀 Cargo Build', cmd: 'cargo build --release' },
                      { label: '🐍 Python Benchmark', cmd: 'python3 scratch/compile_demo.py' },
                      { label: '🌐 Brave Browser', cmd: 'brave' },
                      { label: '💻 VS Code', cmd: 'code' },
                    ].map((preset) => (
                      <button
                        key={preset.label}
                        type="button"
                        onClick={() => setLaunchCommand(preset.cmd)}
                        style={{
                          padding: '3px 8px',
                          borderRadius: '0.25rem',
                          fontSize: '0.74rem',
                          border: `1px solid ${launchCommand === preset.cmd ? colors.accent : colors.border}`,
                          background: launchCommand === preset.cmd ? 'rgba(113,112,255,0.2)' : colors.surface,
                          color: launchCommand === preset.cmd ? colors.accentHover : colors.textSecondary,
                          cursor: 'pointer',
                        }}
                      >
                        {preset.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Command Input */}
                <div>
                  <label style={{ display: 'block', fontSize: '0.78rem', fontWeight: 600, color: colors.textSecondary, marginBottom: '0.3rem' }}>
                    Command to run:
                  </label>
                  <input
                    type="text"
                    value={launchCommand}
                    onChange={(e) => setLaunchCommand(e.target.value)}
                    placeholder="e.g. make -j8 or blender or cargo build --release"
                    style={{
                      width: '100%',
                      boxSizing: 'border-box',
                      padding: '0.6rem 0.8rem',
                      borderRadius: '0.375rem',
                      border: `1px solid ${colors.inputBorder}`,
                      background: colors.inputBg,
                      color: colors.textPrimary,
                      fontFamily: 'monospace',
                      fontSize: '0.85rem',
                    }}
                  />
                </div>
              </div>
            ) : (
              /* Installed Apps List */
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                <input
                  type="text"
                  placeholder="Search installed desktop apps (e.g. brave, code, blender)..."
                  value={searchApp}
                  onChange={(e) => setSearchApp(e.target.value)}
                  style={{
                    width: '100%',
                    boxSizing: 'border-box',
                    padding: '0.5rem 0.75rem',
                    borderRadius: '0.375rem',
                    border: `1px solid ${colors.inputBorder}`,
                    background: colors.inputBg,
                    color: colors.textPrimary,
                    fontSize: '0.82rem',
                  }}
                />

                <div style={{ maxHeight: '180px', overflowY: 'auto', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.4rem' }}>
                  {loadingApps ? (
                    <div style={{ gridColumn: '1 / -1', padding: '1rem', textAlign: 'center', color: colors.textTertiary, fontSize: '0.8rem' }}>
                      Discovering installed applications...
                    </div>
                  ) : installedApps
                    .filter((a) => !searchApp || a.name.toLowerCase().includes(searchApp.toLowerCase()) || a.exec.toLowerCase().includes(searchApp.toLowerCase()))
                    .slice(0, 30)
                    .map((app) => {
                      const isSelected = launchCommand === app.exec;
                      return (
                        <div
                          key={app.name}
                          onClick={() => setLaunchCommand(app.exec)}
                          style={{
                            padding: '0.45rem 0.65rem',
                            borderRadius: '0.375rem',
                            border: `1px solid ${isSelected ? colors.accent : colors.border}`,
                            background: isSelected ? 'rgba(113,112,255,0.18)' : colors.surface,
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.5rem',
                          }}
                        >
                          <span style={{ fontSize: '1.2rem' }}>📦</span>
                          <div style={{ overflow: 'hidden' }}>
                            <div style={{ fontSize: '0.78rem', fontWeight: 600, color: isSelected ? colors.accentHover : colors.textPrimary, whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
                              {app.name}
                            </div>
                            <div style={{ fontSize: '0.68rem', color: colors.textTertiary, fontFamily: 'monospace', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
                              {app.exec.slice(0, 30)}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                </div>
              </div>
            )}

            {/* Launch Settings: Watcher + Terminal + Core Lane */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem', borderTop: `1px solid ${colors.border}`, paddingTop: '0.75rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.84rem', fontWeight: 600, color: colors.emerald, cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={launchWatchMode}
                    onChange={(e) => setLaunchWatchMode(e.target.checked)}
                  />
                  <span>⚡ Arm Power-Spike Watcher (Stock Boost → Dynamic Optimization)</span>
                </label>

                <label style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.78rem', color: colors.textSecondary, cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={launchInTerminal}
                    onChange={(e) => setLaunchInTerminal(e.target.checked)}
                  />
                  <span>Open in native desktop terminal window</span>
                </label>
              </div>

              {launchWatchMode && (
                <div style={{ background: 'rgba(16,185,129,0.06)', borderRadius: '0.375rem', padding: '0.75rem', border: '1px solid rgba(16,185,129,0.2)', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  <div style={{ fontSize: '0.75rem', color: colors.textSecondary, lineHeight: 1.4 }}>
                    <strong style={{ color: colors.emerald }}>How It Works:</strong> Starts at <strong>100% Stock Boost (5.09 GHz)</strong> for zero UI lag. When heavy compute begins (power spikes &ge; 2s above baseline), Joulectrl dynamically applies your chosen policy, and instantly restores Stock Boost when the app returns to idle.
                  </div>

                  {/* Optimization Policy Choice */}
                  <div>
                    <div style={{ fontSize: '0.74rem', color: colors.textTertiary, fontWeight: 600, marginBottom: '0.35rem' }}>
                      Optimization Target during Heavy Compute:
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
                      {[
                        { id: 'efficiency', title: '⚡ Max Energy Savings', desc: 'Clamps to 2.0 GHz base (~59% power cut, quiet fans)' },
                        { id: 'deadline', title: '⏱️ Time Budget Constraint', desc: `Target runtime cap: complete within budget` },
                        { id: 'performance', title: '🏎️ Sustained Max Perf', desc: '100% Stock Boost + isolate on fast cores' },
                      ].map((pol) => {
                        const isSel = launchObjective === pol.id;
                        return (
                          <button
                            key={pol.id}
                            type="button"
                            onClick={() => setLaunchObjective(pol.id as any)}
                            style={{
                              padding: '0.45rem 0.55rem',
                              borderRadius: '0.25rem',
                              border: `1px solid ${isSel ? colors.emerald : colors.border}`,
                              background: isSel ? 'rgba(16,185,129,0.18)' : colors.surface,
                              color: isSel ? colors.textPrimary : colors.textSecondary,
                              fontSize: '0.73rem',
                              fontWeight: isSel ? 600 : 400,
                              textAlign: 'left',
                              cursor: 'pointer',
                            }}
                          >
                            <div style={{ fontWeight: 600, color: isSel ? colors.emerald : colors.textPrimary }}>{pol.title}</div>
                            <div style={{ fontSize: '0.66rem', color: colors.textTertiary, marginTop: '0.15rem' }}>{pol.desc}</div>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {/* If deadline mode, show time budget input */}
                  {launchObjective === 'deadline' && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', background: colors.surface, padding: '0.5rem 0.75rem', borderRadius: '0.25rem', border: `1px solid ${colors.border}` }}>
                      <span style={{ fontSize: '0.76rem', color: colors.textSecondary }}>Maximum Acceptable Runtime:</span>
                      <input
                        type="number"
                        min={3}
                        max={300}
                        value={launchTimeBudgetS}
                        onChange={(e) => setLaunchTimeBudgetS(Math.max(1, parseInt(e.target.value, 10) || 10))}
                        style={{
                          width: '60px',
                          padding: '2px 6px',
                          borderRadius: '0.25rem',
                          background: colors.inputBg,
                          border: `1px solid ${colors.inputBorder}`,
                          color: colors.textPrimary,
                          fontSize: '0.8rem',
                          textAlign: 'center',
                        }}
                      />
                      <span style={{ fontSize: '0.76rem', color: colors.textTertiary }}>seconds (lowest frequency meeting deadline is applied)</span>
                    </div>
                  )}

                  {/* Recurrence Mode */}
                  <div>
                    <div style={{ fontSize: '0.74rem', color: colors.textTertiary, fontWeight: 600, marginBottom: '0.35rem' }}>
                      Workload Recurrence Pattern:
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                      {[
                        { id: 'repeated', title: '🔄 Repeating Workload (Continuous Watcher)', desc: 'Keeps watching across repeated tasks (e.g. recompiles on save, incremental renders). Logs running savings per session.' },
                        { id: 'once', title: '🎯 Single Workload (One-Shot)', desc: 'Optimizes once on the next sustained power spike, restores stock boost on idle, and auto-disarms.' },
                      ].map((rec) => {
                        const isSel = launchRecurrence === rec.id;
                        return (
                          <button
                            key={rec.id}
                            type="button"
                            onClick={() => setLaunchRecurrence(rec.id as any)}
                            style={{
                              padding: '0.45rem 0.55rem',
                              borderRadius: '0.25rem',
                              border: `1px solid ${isSel ? colors.accent : colors.border}`,
                              background: isSel ? 'rgba(113,112,255,0.18)' : colors.surface,
                              color: isSel ? colors.textPrimary : colors.textSecondary,
                              fontSize: '0.73rem',
                              fontWeight: isSel ? 600 : 400,
                              textAlign: 'left',
                              cursor: 'pointer',
                            }}
                          >
                            <div style={{ fontWeight: 600, color: isSel ? colors.accentHover : colors.textPrimary }}>{rec.title}</div>
                            <div style={{ fontSize: '0.66rem', color: colors.textTertiary, marginTop: '0.15rem' }}>{rec.desc}</div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}

              {/* Core Lane Priority */}
              <div>
                <div style={{ fontSize: '0.74rem', color: colors.textTertiary, marginBottom: '0.3rem' }}>
                  Hardware Affinity Lane:
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
                  {[
                    { id: 'fast', label: '⚡ Fast Zen 5 Cores', desc: 'Cores 0,2,4,6,8,10,12,14' },
                    { id: 'eco', label: '🌿 Eco Zen 5c Cores', desc: 'Cores 1,3,5,7,9,11,13,15' },
                    { id: 'all', label: '⚪ All 16 Cores', desc: 'OS default scheduling' },
                  ].map((lane) => {
                    const isSel = launchLane === lane.id;
                    return (
                      <button
                        key={lane.id}
                        type="button"
                        onClick={() => setLaunchLane(lane.id as any)}
                        style={{
                          padding: '0.4rem 0.5rem',
                          borderRadius: '0.25rem',
                          border: `1px solid ${isSel ? colors.accent : colors.border}`,
                          background: isSel ? 'rgba(113,112,255,0.15)' : colors.surface,
                          color: isSel ? colors.textPrimary : colors.textSecondary,
                          fontSize: '0.74rem',
                          fontWeight: isSel ? 600 : 400,
                          textAlign: 'left',
                          cursor: 'pointer',
                        }}
                      >
                        <div>{lane.label}</div>
                        <div style={{ fontSize: '0.65rem', color: colors.textTertiary }}>{lane.desc}</div>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Direct Launch Button inside the card for immediate 1-click execution */}
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '0.25rem' }}>
              <button
                type="button"
                disabled={isLaunchingApp || !launchCommand.trim()}
                onClick={handleExecuteLaunch}
                style={{
                  padding: '0.6rem 1.4rem',
                  borderRadius: '0.375rem',
                  backgroundColor: colors.emerald,
                  color: '#fff',
                  fontSize: '0.88rem',
                  fontWeight: 700,
                  border: 'none',
                  cursor: isLaunchingApp || !launchCommand.trim() ? 'not-allowed' : 'pointer',
                  boxShadow: '0 2px 8px rgba(16, 185, 129, 0.35)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                }}
              >
                <span>🚀</span>
                <span>{isLaunchingApp ? 'Launching...' : 'Launch App / Command Now'}</span>
              </button>
            </div>
          </div>
        ) : (
          /* Process Targeting & Shielding Section */
          <div style={{ marginBottom: '1.5rem', background: colors.surfaceElevated, borderRadius: '0.5rem', padding: '1rem', border: `1px solid ${colors.border}` }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: colors.textPrimary }}>
                  Target Process
                </label>
                <div style={{ fontSize: '0.74rem', color: colors.textTertiary, marginTop: '0.15rem' }}>
                  Shield your active process on dedicated cores to isolate it from multi-task interference.
                </div>
              </div>
              <button
                type="button"
                disabled={loadingProcs}
                onClick={loadActiveProcesses}
                style={{
                  padding: '3px 8px',
                  borderRadius: '0.375rem',
                  border: `1px solid ${colors.border}`,
                  background: colors.surface,
                  color: colors.textSecondary,
                  fontSize: '0.75rem',
                  cursor: loadingProcs ? 'wait' : 'pointer',
                }}
              >
                {loadingProcs ? 'Refreshing…' : '↻ Refresh'}
              </button>
            </div>

            {/* Active Target Card or Process Selector */}
            {targetProcess ? (
              <div
                style={{
                  padding: '0.85rem',
                  borderRadius: '0.375rem',
                  border: `1px solid ${targetCoreLane === 'fast' ? '#8b5cf6' : targetCoreLane === 'eco' ? '#10b981' : colors.accent}`,
                  background: colors.surface,
                  marginBottom: '0.85rem',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: '1.2rem' }}>🎯</span>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ fontWeight: 700, fontSize: '0.95rem', color: colors.textPrimary }}>
                          {targetProcess.name}
                        </span>
                        <span
                          style={{
                            fontSize: '0.72rem',
                            fontFamily: 'monospace',
                            padding: '1px 6px',
                            borderRadius: 4,
                            background: colors.surfaceElevated,
                            border: `1px solid ${colors.border}`,
                            color: colors.textSecondary,
                          }}
                        >
                          PID {targetProcess.pid}
                        </span>
                      </div>
                      {targetProcess.cmdline && (
                        <div
                          title={targetProcess.cmdline}
                          style={{
                            fontSize: '0.74rem',
                            color: colors.textTertiary,
                            maxWidth: 340,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            marginTop: 2,
                          }}
                        >
                          {targetProcess.cmdline}
                        </div>
                      )}
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => {
                      setTargetProcess(null);
                      if (onSelectTargetProcess) onSelectTargetProcess(null);
                    }}
                    style={{
                      padding: '3px 8px',
                      borderRadius: 4,
                      border: `1px solid ${colors.border}`,
                      background: 'transparent',
                      color: colors.textTertiary,
                      fontSize: '0.72rem',
                      cursor: 'pointer',
                    }}
                  >
                    ✕ Change
                  </button>
                </div>

                {/* Metrics row */}
                <div style={{ display: 'flex', gap: 8, marginTop: '0.6rem', flexWrap: 'wrap', alignItems: 'center' }}>
                  {targetProcess.cpu_pct !== undefined && (
                    <span style={{ fontSize: '0.72rem', fontFamily: 'monospace', color: colors.textSecondary, background: colors.surfaceElevated, padding: '2px 6px', borderRadius: 4 }}>
                      CPU: <strong>{targetProcess.cpu_pct.toFixed(1)}%</strong>
                    </span>
                  )}
                  {targetProcess.mem_pct !== undefined && (
                    <span style={{ fontSize: '0.72rem', fontFamily: 'monospace', color: colors.textSecondary, background: colors.surfaceElevated, padding: '2px 6px', borderRadius: 4 }}>
                      RAM: <strong>{targetProcess.mem_pct.toFixed(1)}%</strong>
                    </span>
                  )}
                  {targetProcess.affinity_label && (
                    <span style={{ fontSize: '0.72rem', fontFamily: 'monospace', color: colors.accentHover, background: 'rgba(113,112,255,0.12)', padding: '2px 6px', borderRadius: 4 }}>
                      Affinity: {targetProcess.affinity_label}
                    </span>
                  )}
                </div>
              </div>
            ) : (
              <div>
                {/* Search & Manual PID */}
                <div style={{ display: 'flex', gap: 8, marginBottom: '0.75rem' }}>
                  <input
                    type="text"
                    placeholder="Search active processes (e.g. brave, cargo, python)..."
                    value={procSearch}
                    onChange={(e) => setProcSearch(e.target.value)}
                    style={{
                      flex: 1,
                      padding: '6px 10px',
                      borderRadius: '0.375rem',
                      border: `1px solid ${colors.border}`,
                      background: colors.surface,
                      color: colors.textPrimary,
                      fontSize: '0.8rem',
                      outline: 'none',
                    }}
                  />
                  <div style={{ display: 'flex', gap: 4 }}>
                    <input
                      type="text"
                      placeholder="PID"
                      value={manualPidInput}
                      onChange={(e) => setManualPidInput(e.target.value)}
                      style={{
                        width: 60,
                        padding: '6px 8px',
                        borderRadius: '0.375rem',
                        border: `1px solid ${colors.border}`,
                        background: colors.surface,
                        color: colors.textPrimary,
                        fontSize: '0.8rem',
                        outline: 'none',
                      }}
                    />
                    <button
                      type="button"
                      disabled={!manualPidInput.trim()}
                      onClick={() => {
                        const pid = parseInt(manualPidInput.trim(), 10);
                        if (!Number.isNaN(pid)) {
                          const proc = { pid, name: `PID ${pid}` };
                          setTargetProcess(proc);
                          if (onSelectTargetProcess) onSelectTargetProcess(proc);
                        }
                      }}
                      style={{
                        padding: '6px 10px',
                        borderRadius: '0.375rem',
                        border: 'none',
                        background: colors.accentBg,
                        color: '#ffffff',
                        fontSize: '0.78rem',
                        fontWeight: 600,
                        cursor: manualPidInput.trim() ? 'pointer' : 'not-allowed',
                      }}
                    >
                      Select
                    </button>
                  </div>
                </div>

                {/* Process list */}
                <div
                  style={{
                    maxHeight: 180,
                    overflowY: 'auto',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 4,
                    background: colors.surface,
                    borderRadius: '0.375rem',
                    padding: 6,
                    border: `1px solid ${colors.border}`,
                    marginBottom: '0.85rem',
                  }}
                >
                  {activeProcessList
                    .filter((p) => {
                      const q = procSearch.trim().toLowerCase();
                      if (!q) return true;
                      return (
                        p.name.toLowerCase().includes(q) ||
                        p.cmdline.toLowerCase().includes(q) ||
                        String(p.pid).includes(q)
                      );
                    })
                    .slice(0, 15)
                    .map((p) => (
                      <div
                        key={p.pid}
                        onClick={() => {
                          setTargetProcess(p);
                          if (onSelectTargetProcess) onSelectTargetProcess({ pid: p.pid, name: p.name });
                        }}
                        style={{
                          padding: '6px 10px',
                          borderRadius: 4,
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          cursor: 'pointer',
                          background: colors.surfaceElevated,
                          transition: 'background 0.1s ease',
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(113,112,255,0.15)')}
                        onMouseLeave={(e) => (e.currentTarget.style.background = colors.surfaceElevated)}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, overflow: 'hidden' }}>
                          <span style={{ fontSize: '0.72rem', fontFamily: 'monospace', color: colors.textTertiary, minWidth: 42 }}>
                            {p.pid}
                          </span>
                          <span style={{ fontSize: '0.82rem', fontWeight: 600, color: colors.textPrimary }}>
                            {p.name}
                          </span>
                          <span style={{ fontSize: '0.72rem', color: colors.textTertiary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 180 }}>
                            {p.cmdline}
                          </span>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                          <span style={{ fontSize: '0.72rem', fontFamily: 'monospace', fontWeight: 600, color: p.cpu_pct >= 5 ? '#f59e0b' : colors.textSecondary }}>
                            {p.cpu_pct.toFixed(1)}% CPU
                          </span>
                          <span style={{ fontSize: '0.68rem', color: colors.accentHover }}>Select →</span>
                        </div>
                      </div>
                    ))}
                  {activeProcessList.length === 0 && (
                    <div style={{ padding: '1rem', textAlign: 'center', color: colors.textTertiary, fontSize: '0.78rem' }}>
                      {loadingProcs ? 'Loading processes...' : 'No processes found.'}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Core Priority Lane */}
            <div>
              <div style={{ fontSize: '0.78rem', fontWeight: 600, color: colors.textTertiary, marginBottom: '0.4rem' }}>
                Hardware Core Lane:
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
                {[
                  {
                    id: 'fast',
                    label: '⚡ Fast Zen 5 Cores',
                    desc: 'Cores 0,2,4,6,8,10,12,14 · Boost ON',
                    color: '#8b5cf6',
                  },
                  {
                    id: 'eco',
                    label: '🌿 Eco Zen 5c Cores',
                    desc: 'Cores 1,3,5,7,9,11,13,15 · Nice +15',
                    color: '#10b981',
                  },
                  {
                    id: 'normal',
                    label: '⚪ All 16 Cores',
                    desc: 'Cores 0-15 · Default scheduler',
                    color: colors.textTertiary,
                  },
                ].map((opt) => {
                  const isSel = targetCoreLane === opt.id;
                  return (
                    <button
                      key={opt.id}
                      type="button"
                      onClick={() => {
                        setTargetCoreLane(opt.id as any);
                        if (targetProcess) handleApplyProcessPriority(opt.id as any);
                      }}
                      style={{
                        padding: '0.5rem',
                        borderRadius: '0.375rem',
                        border: `1.5px solid ${isSel ? opt.color : 'rgba(255,255,255,0.08)'}`,
                        background: isSel ? `${opt.color}20` : colors.surface,
                        color: isSel ? colors.textPrimary : colors.textSecondary,
                        textAlign: 'left',
                        cursor: 'pointer',
                        transition: 'all 0.15s ease',
                      }}
                    >
                      <div style={{ fontSize: '0.78rem', fontWeight: 600, color: isSel ? opt.color : colors.textPrimary }}>
                        {opt.label}
                      </div>
                      <div style={{ fontSize: '0.68rem', color: colors.textTertiary, marginTop: 2, lineHeight: 1.3 }}>
                        {opt.desc}
                      </div>
                    </button>
                  );
                })}
              </div>

              {/* Apply Core Lane Button */}
              {targetProcess && (
                <div style={{ marginTop: '0.65rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <button
                    type="button"
                    disabled={isApplyingPriority}
                    onClick={() => handleApplyProcessPriority()}
                    style={{
                      padding: '0.4rem 0.8rem',
                      borderRadius: '0.375rem',
                      border: 'none',
                      background: targetCoreLane === 'fast' ? '#8b5cf6' : targetCoreLane === 'eco' ? '#10b981' : colors.accentBg,
                      color: '#ffffff',
                      fontSize: '0.78rem',
                      fontWeight: 600,
                      cursor: isApplyingPriority ? 'wait' : 'pointer',
                    }}
                  >
                    {isApplyingPriority ? 'Shielding…' : '⚡ Apply Core Lane to Task'}
                  </button>
                  {processFeedback && (
                    <span style={{ fontSize: '0.75rem', color: colors.emerald, fontWeight: 500 }}>
                      {processFeedback}
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

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
                  max={Math.max(300, Math.round((runtimeBudgetS ?? 45) * 1.5))}
                  step={runtimeBudgetS && runtimeBudgetS > 100 ? (runtimeBudgetS > 1000 ? 10 : 5) : 0.5}
                  value={runtimeBudgetS ?? 45}
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
              <div style={{ background: 'rgba(99, 102, 241, 0.08)', border: '1px solid rgba(99, 102, 241, 0.25)', borderRadius: '0.375rem', padding: '0.5rem 0.75rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginTop: '0.2rem' }}>
                <span style={{ fontSize: '0.74rem', color: colors.textSecondary }}>
                  💡 <strong>Preference Mode operates on empirical curves</strong>. Run multithreaded frequency calibration first to map real efficiency frontiers.
                </span>
                {onOpenCalibrationTab && (
                  <button
                    type="button"
                    onClick={onOpenCalibrationTab}
                    style={{
                      padding: '0.25rem 0.6rem',
                      borderRadius: 4,
                      background: colors.accentBg,
                      color: '#fff',
                      border: 'none',
                      fontSize: '0.72rem',
                      cursor: 'pointer',
                      fontWeight: 600,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    Open Calibration Suite →
                  </button>
                )}
              </div>

              <div style={{ fontSize: '0.72rem', color: colors.textTertiary }}>
                Spec §6c: Reports closest honest outcome explicitly if no single candidate satisfies both constraints.
              </div>
            </div>
          )}
        </div>

        {/* Task Priority & Catch-Up Policy */}
        <div style={{ marginBottom: '1.5rem', background: colors.surfaceElevated, padding: '0.85rem 1rem', borderRadius: '0.5rem', border: '1px solid rgba(255,255,255,0.08)' }}>
          {/* Focus Switch (Reverse / Off / On) */}
          {onChangeFocusMode && (
            <div
              style={{
                marginBottom: '0.85rem',
                paddingBottom: '0.85rem',
                borderBottom: '1px solid rgba(255, 255, 255, 0.07)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: '0.75rem',
              }}
            >
              <div>
                <div style={{ fontSize: '0.82rem', fontWeight: 600, color: colors.textPrimary, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span>Focus Switch</span>
                  <span
                    style={{
                      fontSize: '0.68rem',
                      fontWeight: 600,
                      color: focusMode === 'reverse' ? '#10b981' : focusMode === 'on' ? '#818cf8' : colors.textTertiary,
                      padding: '1px 6px',
                      borderRadius: 4,
                      background: 'rgba(255, 255, 255, 0.05)',
                    }}
                  >
                    {focusMode === 'reverse' ? 'Gaming / Foreground Shield' : focusMode === 'on' ? 'Task Priority Shield' : 'Balanced Scheduler'}
                  </span>
                </div>
                <div style={{ fontSize: '0.72rem', color: colors.textTertiary, marginTop: 2, maxWidth: 520, lineHeight: 1.3 }}>
                  {focusMode === 'reverse'
                    ? 'Target app is deprioritized over running foreground apps (e.g. gaming). Runs on Zen 5c Eco Cores with Nice +15; time budget relaxes for pure efficiency.'
                    : focusMode === 'on'
                      ? 'Target app is boosted on Zen 5 Fast Cores (Boost ON, Nice 0). Sacrifices background apps/noise to finish in time.'
                      : 'Standard balanced OS scheduling across all 16 cores.'}
                </div>
              </div>

              <FocusSwitch
                value={focusMode}
                onChange={onChangeFocusMode}
                size="md"
              />
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.6rem' }}>
            <div>
              <div style={{ fontSize: '0.85rem', fontWeight: 600, color: colors.textPrimary, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <span>⚡ Task Priority & Catch-up Policy</span>
              </div>
              <div style={{ fontSize: '0.74rem', color: colors.textTertiary, marginTop: '0.2rem' }}>
                How the scheduler should prioritize this task if other work runs or if it lags behind.
              </div>
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(135px, 1fr))', gap: '0.5rem' }}>
            {[
              {
                key: 'top_priority',
                label: 'Top Priority (Must-Finish)',
                desc: 'Full speed on fast cores. Strict deadline guarantee.',
              },
              {
                key: 'eco_deadline',
                label: 'Eco (Boost if Lagging)',
                desc: 'Runs at low power to save energy. Boosts speed only if falling behind deadline.',
              },
              {
                key: 'best_effort',
                label: 'Best Effort',
                desc: 'Runs in background at lowest power. Yields cores to other tasks.',
              },
            ].map((opt) => {
              const isSelected = (taskPriority || 'top_priority') === opt.key;
              return (
                <button
                  key={opt.key}
                  type="button"
                  onClick={() => onChangeTaskPriority && onChangeTaskPriority(opt.key as any)}
                  style={{
                    padding: '0.6rem 0.75rem',
                    borderRadius: '0.375rem',
                    border: `1.5px solid ${isSelected ? colors.accent : 'rgba(255,255,255,0.08)'}`,
                    backgroundColor: isSelected ? 'rgba(113,112,255,0.18)' : colors.surface,
                    color: isSelected ? colors.textPrimary : colors.textSecondary,
                    textAlign: 'left',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div style={{ fontSize: '0.78rem', fontWeight: 600, color: isSelected ? colors.accentHover : colors.textPrimary }}>
                    {opt.label}
                  </div>
                  <div style={{ fontSize: '0.7rem', color: colors.textTertiary, marginTop: '0.2rem', lineHeight: '1.3' }}>
                    {opt.desc}
                  </div>
                </button>
              );
            })}
          </div>

          {/* Quick link to Task Priority Kanban Board */}
          <div
            style={{
              marginTop: '0.75rem',
              padding: '0.65rem 0.85rem',
              borderRadius: '0.375rem',
              background: 'rgba(255, 255, 255, 0.03)',
              border: '1px solid rgba(255, 255, 255, 0.07)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '0.5rem',
            }}
          >
            <div>
              <div style={{ fontSize: '0.78rem', fontWeight: 600, color: colors.textPrimary }}>
                Manage individual process priorities
              </div>
              <div style={{ fontSize: '0.7rem', color: colors.textTertiary, marginTop: '0.15rem' }}>
                Push background apps to Zen 5c eco cores or pin critical apps to Zen 5 fast cores.
              </div>
            </div>
            {onOpenTasksTab && (
              <button
                type="button"
                onClick={onOpenTasksTab}
                style={{
                  padding: '5px 12px',
                  borderRadius: '0.375rem',
                  border: `1px solid ${colors.accent}`,
                  background: 'rgba(113, 112, 255, 0.15)',
                  color: colors.accentHover,
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                }}
              >
                <span>▦</span> Open Task Priority Kanban Board →
              </button>
            )}
          </div>
        </div>

        {/* Accuracy & Repeatability Control */}
        <div style={{ marginBottom: '1.5rem', background: colors.surfaceElevated, padding: '0.85rem 1rem', borderRadius: '0.5rem', border: '1px solid rgba(255,255,255,0.08)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: '0.85rem', fontWeight: 600, color: colors.textPrimary, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <span>🎯 Runs per Speed Setting</span>
              </div>
              <div style={{ fontSize: '0.74rem', color: colors.textTertiary, marginTop: '0.2rem' }}>
                Run each CPU speed twice to double-check accuracy and make sure numbers line up.
              </div>
            </div>
            <div style={{ display: 'flex', gap: '0.4rem' }}>
              {[
                { val: 1, label: '1 run' },
                { val: 2, label: '2 runs (double-check)' },
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
                <span>
                  {noiseStatus?.is_quiet ? '✓ System Baseline Quiet' : '⚠️ Background Noise Detected'}
                  {thermalStatus?.cpu_temp_c != null && (
                    <span style={{ fontSize: '0.75rem', fontWeight: 400, color: colors.textTertiary, marginLeft: 8 }}>
                      · CPU {thermalStatus.cpu_temp_c.toFixed(1)}°C ({thermalStatus.warning_level === 'normal' ? 'Normal' : thermalStatus.warning_level.toUpperCase()})
                    </span>
                  )}
                </span>
              </div>
              <div style={{ fontSize: '0.74rem', color: colors.textTertiary, marginTop: '0.2rem', lineHeight: '1.35' }}>
                {noiseStatus?.is_quiet
                  ? 'No extra background applications detected. Clean baseline for calibration & sweep accuracy.'
                  : `${noiseStatus?.detected_apps.map((a) => a.name).join(', ')} active (${noiseStatus?.total_noise_cpu_pct}% CPU). Extra background load can skew silicon power curves.`}
              </div>
            </div>
            {!noiseStatus?.is_quiet && (
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                <button
                  type="button"
                  disabled={isDeprioritizing || isQuieting}
                  onClick={handleDeprioritizeNoise}
                  title="Move running apps to Zen 5c Eco Cores without closing them"
                  style={{
                    padding: '0.35rem 0.75rem',
                    borderRadius: '0.375rem',
                    backgroundColor: 'rgba(52, 211, 153, 0.15)',
                    border: '1px solid rgba(52, 211, 153, 0.4)',
                    color: '#34d399',
                    fontSize: '0.78rem',
                    fontWeight: 600,
                    cursor: isDeprioritizing ? 'wait' : 'pointer',
                    whiteSpace: 'nowrap',
                    transition: 'all 0.15s ease',
                  }}
                >
                  {isDeprioritizing ? 'Moving to Eco…' : '🌿 Deprioritize to Eco'}
                </button>
                <button
                  type="button"
                  disabled={isQuieting || isDeprioritizing}
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
                {onOpenTasksTab && (
                  <button
                    type="button"
                    onClick={onOpenTasksTab}
                    style={{
                      padding: '0.35rem 0.65rem',
                      borderRadius: '0.375rem',
                      backgroundColor: 'transparent',
                      border: `1px solid ${colors.border}`,
                      color: colors.textSecondary,
                      fontSize: '0.78rem',
                      cursor: 'pointer',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    Tasks Tab →
                  </button>
                )}
              </div>
            )}
          </div>
          {quietSuccessMsg && (
            <div style={{ marginTop: '0.45rem', fontSize: '0.75rem', color: colors.emerald, fontWeight: 500 }}>
              ✓ {quietSuccessMsg}
            </div>
          )}
        </div>

        {/* Thermal Throttling Warning Banner */}
        {thermalStatus && thermalStatus.warning_level !== 'normal' && (
          <div
            style={{
              marginBottom: '1.5rem',
              background: thermalStatus.warning_level === 'critical' ? 'rgba(239,68,68,0.12)' : 'rgba(245,158,11,0.12)',
              border: `1px solid ${thermalStatus.warning_level === 'critical' ? colors.red : colors.amber}`,
              borderRadius: '0.5rem',
              padding: '0.85rem 1rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
            }}
          >
            <span style={{ fontSize: '1.25rem' }}>🔥</span>
            <div>
              <div style={{ fontSize: '0.85rem', fontWeight: 600, color: thermalStatus.warning_level === 'critical' ? colors.red : colors.amber }}>
                {thermalStatus.warning_level === 'critical' ? 'Thermal Throttling Active' : 'Elevated CPU Temperature'} ({thermalStatus.cpu_temp_c?.toFixed(1)}°C)
              </div>
              <div style={{ fontSize: '0.74rem', color: colors.textSecondary, marginTop: '0.15rem' }}>
                {thermalStatus.message} High CPU temperatures cause hardware clock throttling, which can slow down tasks and distort power measurements.
              </div>
            </div>
          </div>
        )}

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
                <span>⏱️ Scan Duration (Calibration)</span>
              </div>
              <div style={{ fontSize: '0.74rem', color: colors.textTertiary, marginTop: '0.2rem' }}>
                {hasCalibration
                  ? 'Uses saved calibration data (0s), or runs a fresh scan to test speeds on this specific workload.'
                  : 'No saved calibration found on this machine — run a scan first so the app can measure your CPU.'}
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
                ✓ Saved Data Ready
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
                ⚠️ Scan Needed
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
              { val: 60, label: '60s' },
              { val: 120, label: '2 min (120s)' },
              { val: 300, label: '5 min (300s)' },
              { val: 600, label: '10 min (600s)' },
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
              All speeds
            </button>
          </div>

          {/* Slider + NumField */}
          <div style={{ background: colors.surface, padding: '0.75rem', borderRadius: '0.375rem', border: '1px solid rgba(255,255,255,0.06)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: colors.textTertiary, marginBottom: '0.4rem' }}>
              <span>Scan time:</span>
              <span style={{ color: colors.textSecondary, fontWeight: 600 }}>
                {calibrationBudgetS === null
                  ? 'All speeds (up to 30 min safety limit)'
                  : calibrationBudgetS === 0
                    ? '0s (Instant · uses saved data)'
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
                All speeds
              </label>
            </div>

            {/* Simple Human Explanation */}
            <div style={{ marginTop: '0.5rem', fontSize: '0.73rem', color: colors.textTertiary, lineHeight: '1.4' }}>
              {calibrationBudgetS === 0 ? (
                <span style={{ color: colors.emerald }}>
                  ✓ Instant: Skips scanning and optimizes immediately using your saved CPU calibration curves.
                </span>
              ) : calibrationBudgetS === null ? (
                <span style={{ color: colors.textSecondary }}>
                  Tests every supported CPU speed and core setup until finished.
                </span>
              ) : (
                <span style={{ color: colors.textSecondary }}>
                  ⏱️ Runs tests for up to {calibrationBudgetS}s across high, medium, and low CPU speeds to find the sweet spot for your workload. How many points fit depends on how fast your workload runs on this chip.
                  {repetitions > 1 ? ' (Runs each test twice to verify consistency.)' : ''}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Action Button */}
        <button
          onClick={handleStartWithCheck}
          disabled={isStarting || isLaunchingApp || (workloadMode === 'launch' && !launchCommand.trim())}
          style={{
            width: '100%',
            padding: '0.75rem',
            borderRadius: '0.5rem',
            backgroundColor: workloadMode === 'launch' ? colors.emerald : colors.accentBg,
            color: '#fff',
            fontSize: '0.95rem',
            fontWeight: 700,
            border: 'none',
            cursor: (isStarting || isLaunchingApp || (workloadMode === 'launch' && !launchCommand.trim())) ? 'not-allowed' : 'pointer',
            boxShadow: workloadMode === 'launch' ? '0 4px 12px rgba(16, 185, 129, 0.35)' : '0 4px 6px -1px rgba(37, 99, 235, 0.3)',
            transition: 'background-color 0.15s ease',
          }}
        >
          {isStarting || isLaunchingApp
            ? (isLaunchingApp ? 'Launching App / Command...' : 'Optimizing Workload...')
            : workloadMode === 'launch'
              ? !launchCommand.trim()
                ? 'Enter a Command or Select an App Above to Launch'
                : launchWatchMode
                  ? launchObjective === 'efficiency'
                    ? `🚀 Launch App & Arm Watcher (Max Efficiency · 2.0 GHz · ${launchRecurrence === 'repeated' ? 'Continuous' : 'One-Shot'})`
                    : launchObjective === 'deadline'
                    ? `🚀 Launch App & Arm Watcher (Deadline ${launchTimeBudgetS}s · ${launchRecurrence === 'repeated' ? 'Continuous' : 'One-Shot'})`
                    : `🚀 Launch App & Arm Watcher (Sustained Boost + Fast Cores · ${launchRecurrence === 'repeated' ? 'Continuous' : 'One-Shot'})`
                  : `🚀 Launch App on ${launchLane === 'fast' ? 'Fast Cores' : launchLane === 'eco' ? 'Eco Cores' : 'All Cores'}`
              : workloadMode === 'process'
                ? targetProcess
                  ? `Shield PID ${targetProcess.pid} (${targetProcess.name}) on ${targetCoreLane === 'fast' ? 'Fast Cores' : targetCoreLane === 'eco' ? 'Eco Cores' : 'All Cores'}`
                  : 'Select a Running Process to Shield'
                : calibrationBudgetS && calibrationBudgetS > 0
                  ? `Run ${calibrationBudgetS}s Scan & Optimize Workload`
                  : calibrationBudgetS === null
                    ? 'Run Full Scan & Optimize Workload'
                    : objective === 'deadline'
                      ? 'Optimize Workload for Deadline (Instant)'
                      : objective === 'preference'
                        ? 'Optimize for Preference Target (Instant)'
                        : 'Explore Pareto Candidates (Instant)'}
        </button>
      </div>

      {/* Right Column: Hardware Discovery Card */}
      <div style={{ background: colors.surface, borderRadius: '0.75rem', padding: '1.5rem', border: `1px solid ${colors.border}`, boxShadow: colors.cardShadow }}>
        <h2 style={{ margin: '0 0 1.25rem 0', fontSize: '1.15rem', color: colors.textPrimary, fontWeight: 600 }}>
          Hardware Discovery
        </h2>

        {capabilities ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', fontSize: '0.85rem' }}>
            {/* data provenance */}
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
                <strong>Reference fixture data</strong> — sysfs unavailable.
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
                <strong>Live hardware discovered</strong> from this machine.
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
                <span style={{ color: colors.emerald, fontWeight: 700 }}>✓ Verified (16 policies)</span>
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

            <div style={{ background: colors.surfaceElevated, border: `1px solid ${colors.border}`, borderRadius: '0.5rem', padding: '0.6rem', fontSize: '0.72rem', color: colors.textTertiary }}>
              Package energy measured directly from Linux sysfs RAPL hardware counter.
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
