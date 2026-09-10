import React, { useEffect, useRef, useState } from 'react';
import {
  fetchWatchStatus,
  startWatch,
  stopWatch,
  armWatch,
  launchAndArm,
  disarmWatch,
  fetchUserProcesses,
  UserProcess,
} from '../api';
import { WatchStatus } from '../types';
import { colors } from '../design';

interface WatchSegmentResult {
  segment_id: string;
  onset_ts: string | null;
  end_ts: string | null;
  duration_s: number;
  estimated_energy_j: number | null;
  energy_available: boolean;
  suggested_budget_s: number;
  mode: string;
  note: string;
}

interface WatchPanelProps {
  onApplySuggestedBudget: (budgetS: number, durationS?: number) => void;
}

const SAMPLE_HISTORY = 60;

const PRESET_COMMANDS = [
  { label: 'Real GCC 10s+ Compile', cmd: 'make -C scratch/zstd clean && make -C scratch/zstd -j8' },
  { label: 'Cargo Build Release', cmd: 'cargo build --release' },
  { label: 'Blender Render', cmd: 'blender -b -f 1' },
  { label: 'Python Test Suite', cmd: 'pytest tests/unit/test_compute_kernel.py' },
];

export const WatchPanel: React.FC<WatchPanelProps> = ({ onApplySuggestedBudget }) => {
  const [status, setStatus] = useState<WatchStatus | null>(null);
  const [isToggling, setIsToggling] = useState<boolean>(false);
  const [latestSegment, setLatestSegment] = useState<WatchSegmentResult | null>(null);
  const [samples, setSamples] = useState<{ t: string; w: number; inBand: boolean }[]>([]);
  const [liveState, setLiveState] = useState<{
    state: string;
    baseline_median_w: number | null;
    control_state?: string;
    target_pid?: number | null;
    target_process_name?: string | null;
    total_saved_energy_j?: number;
    active_sessions_count?: number;
  } | null>(null);
  const esRef = useRef<EventSource | null>(null);

  // Active Pinning & Launch state
  const [launchCmd, setLaunchCmd] = useState<string>('make -C scratch/zstd clean && make -C scratch/zstd -j8');
  const [launchInTerminal, setLaunchInTerminal] = useState<boolean>(true);
  const [watchObjective, setWatchObjective] = useState<'efficiency' | 'deadline' | 'performance'>('efficiency');
  const [watchRecurrence, setWatchRecurrence] = useState<'repeated' | 'once'>('repeated');
  const [watchTimeBudgetS, setWatchTimeBudgetS] = useState<number>(20);
  const [processes, setProcesses] = useState<UserProcess[]>([]);
  const [selectedPid, setSelectedPid] = useState<string>('');
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const refreshStatus = async () => {
    try {
      const st = await fetchWatchStatus();
      setStatus(st);
    } catch (e) {
      console.error(e);
    }
  };

  const loadProcesses = async () => {
    try {
      const res = await fetchUserProcesses(60);
      if (res.processes) {
        setProcesses(res.processes);
      }
    } catch {
      // Non-fatal
    }
  };

  useEffect(() => {
    loadProcesses();
  }, []);

  // Live SSE: samples, state transitions, closed segments (real detector).
  useEffect(() => {
    if (!status?.active) {
      esRef.current?.close();
      esRef.current = null;
      return;
    }
    const es = new EventSource('/api/watch/events');
    esRef.current = es;
    es.addEventListener('watch_sample', (ev) => {
      try {
        const d = JSON.parse((ev as MessageEvent).data);
        setSamples((prev) => [
          ...prev.slice(-SAMPLE_HISTORY + 1),
          { t: d.timestamp, w: d.power_w, inBand: d.in_idle_band },
        ]);
      } catch { /* ignore */ }
    });
    es.addEventListener('watch_state', (ev) => {
      try {
        const d = JSON.parse((ev as MessageEvent).data);
        setLiveState(d);
      } catch { /* ignore */ }
    });
    es.addEventListener('watch_segment', (ev) => {
      try {
        setLatestSegment(JSON.parse((ev as MessageEvent).data));
        refreshStatus();
      } catch { /* ignore */ }
    });
    es.onerror = () => es.close();
    return () => es.close();
  }, [status?.active]);

  useEffect(() => {
    refreshStatus();
    const interval = setInterval(refreshStatus, 2000);
    return () => clearInterval(interval);
  }, []);

  const handleTogglePassive = async () => {
    try {
      setIsToggling(true);
      if (status?.active) {
        const res = await stopWatch();
        if (res.segments && res.segments.length > 0) {
          setLatestSegment(res.segments[res.segments.length - 1]);
        }
      } else {
        setSamples([]);
        setLatestSegment(null);
        setLiveState(null);
        await startWatch({ idle_grace_s: 18 });
      }
      await refreshStatus();
    } catch (e: any) {
      alert(`Watch mode error: ${e.message}`);
    } finally {
      setIsToggling(false);
    }
  };

  const handleLaunchAndArm = async () => {
    if (!launchCmd.trim()) return;
    try {
      setIsSubmitting(true);
      setActionFeedback(null);
      const res = await launchAndArm({
        command: launchCmd.trim(),
        launch_in_terminal: launchInTerminal,
        optimization_objective: watchObjective,
        recurrence_mode: watchRecurrence,
        time_budget_s: watchObjective === 'deadline' ? watchTimeBudgetS : undefined,
        baseline_w: status?.baseline_median_w ?? undefined,
      });
      const modeDesc =
        watchObjective === 'efficiency'
          ? 'Max Efficiency (2.0 GHz)'
          : watchObjective === 'deadline'
          ? `Deadline ${watchTimeBudgetS}s`
          : 'Sustained Boost + Core Shielding';
      setActionFeedback(`🚀 Launched PID ${res.pid} at Stock Boost! Watcher armed: ${modeDesc} (${watchRecurrence === 'repeated' ? 'Continuous Watcher' : 'One-Shot'}).`);
      await refreshStatus();
    } catch (e: any) {
      setActionFeedback(`❌ Launch error: ${e.message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleArmSelectedPid = async () => {
    const pidNum = parseInt(selectedPid, 10);
    if (isNaN(pidNum) || pidNum <= 0) return;
    try {
      setIsSubmitting(true);
      setActionFeedback(null);
      const proc = processes.find((p) => p.pid === pidNum);
      const res = await armWatch({
        pid: pidNum,
        process_name: proc?.name,
        focus_mode: 'on',
        optimization_objective: watchObjective,
        recurrence_mode: watchRecurrence,
        time_budget_s: watchObjective === 'deadline' ? watchTimeBudgetS : undefined,
        baseline_w: status?.baseline_median_w ?? undefined,
      });
      const modeDesc =
        watchObjective === 'efficiency'
          ? 'Max Efficiency (2.0 GHz)'
          : watchObjective === 'deadline'
          ? `Deadline ${watchTimeBudgetS}s`
          : 'Sustained Boost + Core Shielding';
      setActionFeedback(`🎯 Watcher armed for ${proc?.name ?? 'PID ' + pidNum}: ${modeDesc} (${watchRecurrence === 'repeated' ? 'Continuous Watcher' : 'One-Shot'})!`);
      await refreshStatus();
    } catch (e: any) {
      setActionFeedback(`❌ Arm error: ${e.message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDisarm = async () => {
    try {
      setIsSubmitting(true);
      await disarmWatch();
      setActionFeedback('🛑 Watcher disarmed. Stock boost and normal scheduling restored.');
      await refreshStatus();
    } catch (e: any) {
      setActionFeedback(`❌ Disarm error: ${e.message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const controlState = liveState?.control_state ?? status?.control_state ?? (status?.active ? 'passive_watching' : 'stopped');
  const isArmed = status?.active_control && (controlState === 'stock_idle' || controlState === 'optimized_active');
  const isClamped = controlState === 'optimized_active';
  const targetPid = liveState?.target_pid ?? status?.target_pid;
  const targetName = liveState?.target_process_name ?? status?.target_process_name;
  const totalSavedJ = liveState?.total_saved_energy_j ?? status?.total_saved_energy_j ?? 0;
  const sessionsCount = liveState?.active_sessions_count ?? status?.active_sessions_count ?? 0;

  const stateLabel = liveState?.state ?? status?.state ?? 'idle';
  const power = samples.length > 0 ? samples[samples.length - 1].w : status?.current_power_w;
  const baseline = liveState?.baseline_median_w ?? status?.baseline_median_w;

  const sparkline = () => {
    if (samples.length < 2) return null;
    const ws = samples.map((s) => s.w);
    const min = Math.min(...ws, 5);
    const max = Math.max(...ws, 10);
    const span = Math.max(max - min, 1);
    const pts = samples
      .map((s, i) => `${(i / (samples.length - 1)) * 100},${28 - ((s.w - min) / span) * 26}`)
      .join(' ');
    return (
      <svg viewBox="0 0 100 28" preserveAspectRatio="none" style={{ width: '100%', height: '44px', marginTop: '0.5rem' }}>
        <polyline points={pts} fill="none" stroke={isClamped ? '#06b6d4' : colors.emerald} strokeWidth="1.5" />
      </svg>
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '1050px', margin: '0 auto' }}>
      {/* Dynamic App Launch & Power-Spike Watcher Card (Primary Feature) */}
      <div
        style={{
          background: isClamped
            ? 'linear-gradient(135deg, rgba(6, 182, 212, 0.12) 0%, rgba(16, 185, 129, 0.10) 100%)'
            : isArmed
            ? 'linear-gradient(135deg, rgba(16, 185, 129, 0.08) 0%, rgba(30, 41, 59, 0.6) 100%)'
            : colors.surface,
          padding: '1.5rem',
          borderRadius: '0.875rem',
          border: isClamped
            ? '1.5px solid #06b6d4'
            : isArmed
            ? `1.5px solid ${colors.emerald}`
            : `1px solid ${colors.border}`,
          boxShadow: isClamped
            ? '0 0 20px rgba(6, 182, 212, 0.25)'
            : isArmed
            ? '0 0 15px rgba(16, 185, 129, 0.15)'
            : colors.cardShadow,
          display: 'flex',
          flexDirection: 'column',
          gap: '1.25rem',
          position: 'relative',
        }}
      >
        {/* State Banner */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <span style={{ fontSize: '1.4rem' }}>
                {isClamped ? '⚡' : isArmed ? '🟢' : '🎯'}
              </span>
              <h2 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 700, color: colors.textPrimary }}>
                Dynamic App Optimization (Power-Spike Watcher)
              </h2>
              <span
                style={{
                  fontSize: '0.7rem',
                  fontWeight: 700,
                  padding: '0.2rem 0.6rem',
                  borderRadius: '0.375rem',
                  backgroundColor: isClamped
                    ? 'rgba(6, 182, 212, 0.25)'
                    : isArmed
                    ? 'rgba(16, 185, 129, 0.2)'
                    : 'rgba(255, 255, 255, 0.08)',
                  color: isClamped ? '#06b6d4' : isArmed ? colors.emerald : colors.textTertiary,
                  border: isClamped
                    ? '1px solid #06b6d4'
                    : isArmed
                    ? `1px solid ${colors.emerald}`
                    : '1px solid transparent',
                  letterSpacing: '0.04em',
                }}
              >
                {isClamped
                  ? (status?.optimization_objective === 'performance'
                      ? 'ACTIVE SHIELD ENGAGED (Fast Cores Stock Boost)'
                      : status?.optimization_objective === 'deadline'
                      ? `ACTIVE CLAMP ENGAGED (Deadline Target ${status?.time_budget_s || 20}s)`
                      : 'ACTIVE CLAMP ENGAGED (2.0 GHz Sweet Spot)')
                  : isArmed
                  ? `ARMED · STOCK BOOST (${status?.recurrence_mode === 'once' ? 'One-Shot' : 'Continuous'} · ${status?.optimization_objective === 'performance' ? 'Max Perf' : status?.optimization_objective === 'deadline' ? `Deadline ${status?.time_budget_s || 20}s` : 'Max Efficiency'})`
                  : 'STANDBY / DISARMED'}
              </span>
            </div>

            <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.85rem', color: colors.textSecondary, lineHeight: 1.5 }}>
              {isClamped ? (
                <span>
                  <strong>Sustained heavy compute detected!</strong> CPU clamped to Pareto-optimal 2.0 GHz & Focus Switch prioritized PID {targetPid} ({targetName}). Saving ~35% energy in real-time. Clocks will restore instantly upon task completion.
                </span>
              ) : isArmed ? (
                <span>
                  App {targetName ? <strong>{targetName}</strong> : ''} {targetPid ? `(PID ${targetPid})` : ''} is running at <strong>100% uncapped Stock Boost</strong> for zero UI latency. The watcher is armed and will instantly clamp to the sweet-spot when a sustained power spike begins.
                </span>
              ) : (
                <span>
                  Prevents startup and menu lag. Launch an app or pin a running PID: it stays at <strong>100% Stock Boost</strong> during launch and UI navigation, clamping to the energy sweet spot only during the sustained compute spike.
                </span>
              )}
            </p>
          </div>

          {isArmed && (
            <button
              onClick={handleDisarm}
              disabled={isSubmitting}
              style={{
                padding: '0.5rem 1rem',
                borderRadius: '0.375rem',
                backgroundColor: 'rgba(239, 68, 68, 0.15)',
                color: colors.red,
                fontSize: '0.85rem',
                fontWeight: 600,
                border: `1px solid ${colors.red}`,
                cursor: isSubmitting ? 'wait' : 'pointer',
              }}
            >
              🛑 Disarm & Restore All Clocks
            </button>
          )}
        </div>

        {/* Feedback Alert */}
        {actionFeedback && (
          <div
            style={{
              padding: '0.65rem 0.9rem',
              borderRadius: '0.375rem',
              backgroundColor: actionFeedback.includes('❌') ? 'rgba(239,68,68,0.15)' : 'rgba(16,185,129,0.15)',
              border: `1px solid ${actionFeedback.includes('❌') ? colors.red : colors.emerald}`,
              fontSize: '0.85rem',
              color: colors.textPrimary,
            }}
          >
            {actionFeedback}
          </div>
        )}

        {/* Watcher Strategy: Objective + Recurrence Pattern */}
        <div
          style={{
            background: 'rgba(16,185,129,0.06)',
            borderRadius: '0.5rem',
            padding: '1rem',
            border: '1px solid rgba(16,185,129,0.2)',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.85rem',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
            <div style={{ fontSize: '0.88rem', fontWeight: 700, color: colors.textPrimary, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <span>⚙️</span> Watcher Optimization Strategy
            </div>
            <div style={{ fontSize: '0.74rem', color: colors.textTertiary }}>
              Applied dynamically the moment sustained heavy compute is detected (&ge; 2s)
            </div>
          </div>

          {/* Objective Selector */}
          <div>
            <div style={{ fontSize: '0.75rem', color: colors.textTertiary, fontWeight: 600, marginBottom: '0.4rem' }}>
              Optimization Policy on Power Spike:
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.5rem' }}>
              {[
                { id: 'efficiency', title: '⚡ Max Efficiency (2.0 GHz)', desc: 'Clamps to 2.0 GHz base clock. ~59% power reduction, whisper quiet fans.' },
                { id: 'deadline', title: '⏱️ Time Budget / Deadline', desc: `Target runtime cap: complete task within user deadline.` },
                { id: 'performance', title: '🏎️ Sustained Max Perf', desc: '100% Stock Boost (5.09 GHz) maintained + isolated on Zen 5 fast cores.' },
              ].map((pol) => {
                const isSel = watchObjective === pol.id;
                return (
                  <button
                    key={pol.id}
                    type="button"
                    onClick={() => setWatchObjective(pol.id as any)}
                    style={{
                      padding: '0.55rem 0.65rem',
                      borderRadius: '0.375rem',
                      border: `1px solid ${isSel ? colors.emerald : colors.border}`,
                      background: isSel ? 'rgba(16,185,129,0.18)' : colors.surfaceElevated,
                      color: isSel ? colors.textPrimary : colors.textSecondary,
                      fontSize: '0.76rem',
                      textAlign: 'left',
                      cursor: 'pointer',
                    }}
                  >
                    <div style={{ fontWeight: 600, color: isSel ? colors.emerald : colors.textPrimary }}>{pol.title}</div>
                    <div style={{ fontSize: '0.68rem', color: colors.textTertiary, marginTop: '0.2rem', lineHeight: 1.35 }}>{pol.desc}</div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Time Budget inline input for deadline mode */}
          {watchObjective === 'deadline' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', background: colors.surfaceElevated, padding: '0.55rem 0.75rem', borderRadius: '0.375rem', border: `1px solid ${colors.border}` }}>
              <span style={{ fontSize: '0.78rem', color: colors.textSecondary }}>Maximum Acceptable Runtime:</span>
              <input
                type="number"
                min={3}
                max={300}
                value={watchTimeBudgetS}
                onChange={(e) => setWatchTimeBudgetS(Math.max(1, parseInt(e.target.value, 10) || 10))}
                style={{
                  width: '65px',
                  padding: '3px 8px',
                  borderRadius: '0.25rem',
                  background: colors.inputBg,
                  border: `1px solid ${colors.inputBorder}`,
                  color: colors.textPrimary,
                  fontSize: '0.82rem',
                  textAlign: 'center',
                }}
              />
              <span style={{ fontSize: '0.76rem', color: colors.textTertiary }}>seconds (applies lowest Pareto frequency meeting this deadline)</span>
            </div>
          )}

          {/* Recurrence Mode Selector */}
          <div>
            <div style={{ fontSize: '0.75rem', color: colors.textTertiary, fontWeight: 600, marginBottom: '0.4rem' }}>
              Workload Recurrence Pattern:
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
              {[
                { id: 'repeated', title: '🔄 Repeating Workload (Continuous Watcher)', desc: 'Stays armed across repeated tasks (e.g. recompiles on save, incremental renders). Automatically optimizes each burst and logs running receipts.' },
                { id: 'once', title: '🎯 Single Workload (One-Shot Task)', desc: 'Optimizes once on the next sustained power spike, restores stock boost when task returns to idle, and auto-disarms.' },
              ].map((rec) => {
                const isSel = watchRecurrence === rec.id;
                return (
                  <button
                    key={rec.id}
                    type="button"
                    onClick={() => setWatchRecurrence(rec.id as any)}
                    style={{
                      padding: '0.55rem 0.65rem',
                      borderRadius: '0.375rem',
                      border: `1px solid ${isSel ? colors.accent : colors.border}`,
                      background: isSel ? 'rgba(113,112,255,0.18)' : colors.surfaceElevated,
                      color: isSel ? colors.textPrimary : colors.textSecondary,
                      fontSize: '0.76rem',
                      textAlign: 'left',
                      cursor: 'pointer',
                    }}
                  >
                    <div style={{ fontWeight: 600, color: isSel ? colors.accentHover : colors.textPrimary }}>{rec.title}</div>
                    <div style={{ fontSize: '0.68rem', color: colors.textTertiary, marginTop: '0.2rem', lineHeight: 1.35 }}>{rec.desc}</div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Launch & Pin Controls */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1rem', marginTop: '0.5rem' }}>
          {/* Option A: Launch New Command */}
          <div
            style={{
              background: colors.surfaceElevated,
              padding: '1.1rem',
              borderRadius: '0.5rem',
              border: `1px solid ${colors.border}`,
              display: 'flex',
              flexDirection: 'column',
              gap: '0.75rem',
            }}
          >
            <div style={{ fontSize: '0.85rem', fontWeight: 600, color: colors.textPrimary }}>
              🚀 Option A: Launch Command at Stock Boost
            </div>

            <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
              {PRESET_COMMANDS.map((preset) => (
                <button
                  key={preset.label}
                  onClick={() => setLaunchCmd(preset.cmd)}
                  style={{
                    padding: '0.2rem 0.5rem',
                    fontSize: '0.72rem',
                    borderRadius: '0.25rem',
                    backgroundColor: launchCmd === preset.cmd ? colors.accent : 'rgba(255,255,255,0.06)',
                    color: colors.textPrimary,
                    border: 'none',
                    cursor: 'pointer',
                  }}
                >
                  {preset.label}
                </button>
              ))}
            </div>

            <input
              type="text"
              value={launchCmd}
              onChange={(e) => setLaunchCmd(e.target.value)}
              placeholder="e.g. make -j8 or blender or cargo build"
              style={{
                padding: '0.5rem 0.75rem',
                borderRadius: '0.375rem',
                backgroundColor: colors.inputBg,
                border: `1px solid ${colors.inputBorder}`,
                color: colors.textPrimary,
                fontSize: '0.85rem',
                fontFamily: 'monospace',
              }}
            />

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.78rem', color: colors.textSecondary, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={launchInTerminal}
                  onChange={(e) => setLaunchInTerminal(e.target.checked)}
                />
                Launch in Desktop Terminal
              </label>

              <button
                onClick={handleLaunchAndArm}
                disabled={isSubmitting || !launchCmd.trim()}
                style={{
                  padding: '0.45rem 1rem',
                  borderRadius: '0.375rem',
                  backgroundColor: colors.emerald,
                  color: '#fff',
                  fontSize: '0.82rem',
                  fontWeight: 600,
                  border: 'none',
                  cursor: isSubmitting ? 'wait' : 'pointer',
                }}
              >
                Launch & Arm Watcher
              </button>
            </div>
          </div>

          {/* Option B: Pin Running App */}
          <div
            style={{
              background: colors.surfaceElevated,
              padding: '1.1rem',
              borderRadius: '0.5rem',
              border: `1px solid ${colors.border}`,
              display: 'flex',
              flexDirection: 'column',
              gap: '0.75rem',
            }}
          >
            <div style={{ fontSize: '0.85rem', fontWeight: 600, color: colors.textPrimary }}>
              🎯 Option B: Arm on Already Running Process
            </div>

            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <select
                value={selectedPid}
                onChange={(e) => setSelectedPid(e.target.value)}
                style={{
                  flex: 1,
                  padding: '0.5rem',
                  borderRadius: '0.375rem',
                  backgroundColor: colors.inputBg,
                  border: `1px solid ${colors.inputBorder}`,
                  color: colors.textPrimary,
                  fontSize: '0.82rem',
                }}
              >
                <option value="">Select running process ({processes.length} detected)...</option>
                {processes.slice(0, 40).map((p) => (
                  <option key={p.pid} value={p.pid}>
                    {p.name} (PID: {p.pid}) — {p.cpu_pct.toFixed(1)}% CPU
                  </option>
                ))}
              </select>

              <button
                onClick={handleArmSelectedPid}
                disabled={isSubmitting || !selectedPid}
                style={{
                  padding: '0.45rem 1rem',
                  borderRadius: '0.375rem',
                  backgroundColor: colors.accent,
                  color: '#fff',
                  fontSize: '0.82rem',
                  fontWeight: 600,
                  border: 'none',
                  cursor: isSubmitting || !selectedPid ? 'not-allowed' : 'pointer',
                }}
              >
                Arm on PID
              </button>
            </div>

            <div style={{ fontSize: '0.75rem', color: colors.textTertiary, lineHeight: 1.4 }}>
              The selected process keeps normal priority and boost now. Once it spikes into heavy compute, Joulectrl clamps the hardware to sweet-spot clocks.
            </div>
          </div>
        </div>

        {/* Real-time Savings Ticker */}
        {sessionsCount > 0 && (
          <div
            style={{
              background: 'rgba(16, 185, 129, 0.12)',
              border: `1px solid ${colors.emerald}`,
              borderRadius: '0.5rem',
              padding: '0.85rem 1.1rem',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '0.75rem',
            }}
          >
            <div>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: colors.emerald, textTransform: 'uppercase' }}>
                Active Dynamic Optimization Yield
              </div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: colors.textPrimary, marginTop: '0.2rem' }}>
                ⚡ Total Energy Saved: <strong>{totalSavedJ.toFixed(1)} Joules</strong> across {sessionsCount} compute session{sessionsCount > 1 ? 's' : ''}
              </div>
            </div>

            <span
              style={{
                fontSize: '0.75rem',
                color: colors.emerald,
                backgroundColor: 'rgba(16, 185, 129, 0.2)',
                padding: '0.3rem 0.6rem',
                borderRadius: '0.25rem',
                fontWeight: 600,
              }}
            >
              ~35% Hardware Energy Reduction
            </span>
          </div>
        )}
      </div>

      {/* Live Power Metrics Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
        <div style={{ background: colors.surface, padding: '1.25rem', borderRadius: '0.75rem', border: `1px solid ${colors.border}`, boxShadow: colors.cardShadow }}>
          <div style={{ fontSize: '0.75rem', color: colors.textTertiary, textTransform: 'uppercase' }}>Current Package Power</div>
          <div style={{ fontSize: '1.8rem', fontWeight: 700, color: colors.textPrimary, marginTop: '0.3rem' }}>
            {power != null ? `${power.toFixed ? power.toFixed(1) : power} W` : '—'}
          </div>
          {status?.active && sparkline()}
          <div style={{ fontSize: '0.75rem', color: isClamped ? '#06b6d4' : colors.emerald, marginTop: '0.25rem' }}>
            {status?.active ? `● Active Polling (${status?.poll_hz ?? 1} Hz)` : '○ Standby'}
          </div>
        </div>

        <div style={{ background: colors.surface, padding: '1.25rem', borderRadius: '0.75rem', border: `1px solid ${colors.border}`, boxShadow: colors.cardShadow }}>
          <div style={{ fontSize: '0.75rem', color: colors.textTertiary, textTransform: 'uppercase' }}>Rough Idle Baseline</div>
          <div style={{ fontSize: '1.8rem', fontWeight: 700, color: colors.accentHover, marginTop: '0.3rem' }}>
            {baseline != null ? `${baseline.toFixed ? baseline.toFixed(1) : baseline} W` : (status?.active ? 'Observing rough idle…' : 'Auto-detected on arm')}
          </div>
          <div style={{ fontSize: '0.75rem', color: colors.textTertiary, marginTop: '0.25rem' }}>
            {status?.threshold_w != null
              ? `Spike threshold: ${status.threshold_w.toFixed(1)} W (±${(status?.baseline_spread_w ?? 0.5).toFixed(1)} W spread)`
              : baseline != null
              ? `Spike threshold: ${(baseline + Math.max(3.0 * (status?.baseline_spread_w ?? 0.5), 0.35 * baseline, 3.5)).toFixed(1)} W`
              : 'Dynamic auto-threshold on sudden spike'}
          </div>
        </div>

        <div style={{ background: colors.surface, padding: '1.25rem', borderRadius: '0.75rem', border: `1px solid ${colors.border}`, boxShadow: colors.cardShadow }}>
          <div style={{ fontSize: '0.75rem', color: colors.textTertiary, textTransform: 'uppercase' }}>Hardware State</div>
          <div style={{ fontSize: '1.35rem', fontWeight: 700, color: isClamped ? '#06b6d4' : isArmed ? colors.emerald : colors.amber, marginTop: '0.5rem', textTransform: 'capitalize' }}>
            {isClamped ? 'Sweet-Spot Clamped (2.0 GHz)' : isArmed ? 'Stock Boost ON (100% Fast)' : String(stateLabel).replace('_', ' ')}
          </div>
          <div style={{ fontSize: '0.75rem', color: colors.textTertiary, marginTop: '0.25rem' }}>
            {targetName ? `Target: ${targetName} (PID ${targetPid})` : 'Target: System'}
          </div>
        </div>
      </div>

      {/* Suggested Budget & Observation Card */}
      {latestSegment && (
        <div
          style={{
            background: 'rgba(16,185,129,0.18)',
            border: '1.5px solid ' + colors.emerald,
            borderRadius: '0.75rem',
            padding: '1.25rem',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <div>
            <div style={{ fontSize: '0.8rem', color: colors.emerald, fontWeight: 600, textTransform: 'uppercase' }}>
              Detected Task Observation (Idle-to-Idle Window) — {latestSegment.segment_id}
            </div>
            <div style={{ fontSize: '1.1rem', fontWeight: 700, color: colors.textPrimary, marginTop: '0.25rem' }}>
              Observed Duration: {latestSegment.duration_s}s ·{' '}
              {latestSegment.estimated_energy_j != null
                ? `Est. Energy: ${latestSegment.estimated_energy_j} J`
                : 'Energy unavailable'}
            </div>
            <div style={{ fontSize: '0.8rem', color: colors.emerald, marginTop: '0.25rem' }}>
              Suggested runtime budget: <strong>{latestSegment.suggested_budget_s}s</strong> ({latestSegment.note})
            </div>
          </div>

          <button
            onClick={() => onApplySuggestedBudget(latestSegment.suggested_budget_s, latestSegment.duration_s)}
            style={{
              padding: '0.6rem 1.2rem',
              borderRadius: '0.375rem',
              backgroundColor: colors.emerald,
              color: colors.textPrimary,
              fontSize: '0.85rem',
              fontWeight: 600,
              border: 'none',
              cursor: 'pointer',
              boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
            }}
          >
            Apply to Setup Budget Slider →
          </button>
        </div>
      )}

      {/* Passive Mode Controls (Secondary) */}
      <div
        style={{
          background: colors.surface,
          padding: '1rem 1.25rem',
          borderRadius: '0.75rem',
          border: `1px solid ${colors.border}`,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div style={{ fontSize: '0.8rem', color: colors.textTertiary }}>
          <strong>Passive Observation Mode:</strong> Only records power without modifying clock speeds or core affinities.
        </div>

        <button
          onClick={handleTogglePassive}
          disabled={isToggling}
          style={{
            padding: '0.4rem 1rem',
            borderRadius: '0.375rem',
            backgroundColor: status?.active && !status?.active_control ? colors.red : 'rgba(255,255,255,0.08)',
            color: colors.textPrimary,
            fontSize: '0.78rem',
            fontWeight: 600,
            border: 'none',
            cursor: isToggling ? 'wait' : 'pointer',
          }}
        >
          {status?.active && !status?.active_control ? 'Stop Passive Watching' : 'Start Passive Watching'}
        </button>
      </div>
    </div>
  );
};
