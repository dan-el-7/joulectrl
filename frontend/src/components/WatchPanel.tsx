import React, { useEffect, useRef, useState } from 'react';
import { fetchWatchStatus, startWatch, stopWatch } from '../api';
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

export const WatchPanel: React.FC<WatchPanelProps> = ({ onApplySuggestedBudget }) => {
  const [status, setStatus] = useState<WatchStatus | null>(null);
  const [isToggling, setIsToggling] = useState<boolean>(false);
  const [latestSegment, setLatestSegment] = useState<WatchSegmentResult | null>(null);
  const [samples, setSamples] = useState<{ t: string; w: number; inBand: boolean }[]>([]);
  const [liveState, setLiveState] = useState<{ state: string; baseline_median_w: number | null } | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const refreshStatus = async () => {
    try {
      const st = await fetchWatchStatus();
      setStatus(st);
    } catch (e) {
      console.error(e);
    }
  };

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
      } catch { /* ignore malformed frame */ }
    });
    es.addEventListener('watch_state', (ev) => {
      try {
        setLiveState(JSON.parse((ev as MessageEvent).data));
      } catch { /* ignore */ }
    });
    es.addEventListener('watch_segment', (ev) => {
      try {
        setLatestSegment(JSON.parse((ev as MessageEvent).data));
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

  const handleToggle = async () => {
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

  const stateLabel = liveState?.state ?? status?.state ?? 'idle';
  const power = samples.length > 0 ? samples[samples.length - 1].w : status?.current_power_w;
  const baseline = liveState?.baseline_median_w ?? status?.baseline_median_w;

  // Mini sparkline of the live power trace
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
        <polyline points={pts} fill="none" stroke={colors.emerald} strokeWidth="1" />
      </svg>
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '1000px', margin: '0 auto' }}>
      {/* Header */}
      <div
        style={{
          background: colors.surface,
          padding: '1.25rem',
          borderRadius: '0.75rem',
          border: colors.border,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <h2 style={{ margin: 0, fontSize: '1.15rem', color: colors.textPrimary, fontWeight: 600 }}>
              Passive Watch Mode (Idle → Activity → Idle Detection)
            </h2>
            <span
              style={{
                fontSize: '0.65rem',
                fontWeight: 600,
                padding: '0.15rem 0.4rem',
                borderRadius: '0.25rem',
                backgroundColor: 'rgba(255,255,255,0.08)',
                color: colors.textTertiary,
              }}
            >
              Estimate Tier (§6b)
            </span>
          </div>
          <div style={{ fontSize: '0.8rem', color: colors.textTertiary, marginTop: '0.25rem' }}>
            Watches package power passively (0.5–1 Hz) while you run your own task. Automatically suggests a runtime budget.
            {status?.source?.synthetic && (
              <span style={{ color: colors.amber }}> · demo source: synthetic scripted profile (no readable package counter on this machine)</span>
            )}
            {!status?.source?.synthetic && status?.source?.source && (
              <span style={{ color: colors.emerald }}> · live hardware source: {status.source.source}</span>
            )}
          </div>
        </div>

        <button
          onClick={handleToggle}
          disabled={isToggling}
          style={{
            padding: '0.5rem 1.25rem',
            borderRadius: '0.375rem',
            backgroundColor: status?.active ? colors.red : colors.emerald,
            color: colors.textPrimary,
            fontSize: '0.85rem',
            fontWeight: 600,
            border: 'none',
            cursor: isToggling ? 'wait' : 'pointer',
          }}
        >
          {status?.active ? 'Stop Passive Watching' : 'Start Passive Watching'}
        </button>
      </div>

      {/* Live Metrics Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
        <div style={{ background: colors.surface, padding: '1.25rem', borderRadius: '0.75rem', border: colors.border }}>
          <div style={{ fontSize: '0.75rem', color: colors.textTertiary, textTransform: 'uppercase' }}>Current Package Power</div>
          <div style={{ fontSize: '1.8rem', fontWeight: 700, color: colors.textPrimary, marginTop: '0.3rem' }}>
            {power != null ? `${power.toFixed ? power.toFixed(1) : power} W` : '—'}
          </div>
          {status?.active && sparkline()}
          <div style={{ fontSize: '0.75rem', color: colors.emerald, marginTop: '0.25rem' }}>
            {status?.active ? `● Featherweight polling (${status?.poll_hz ?? 1} Hz)` : '○ Standby'}
          </div>
        </div>

        <div style={{ background: colors.surface, padding: '1.25rem', borderRadius: '0.75rem', border: colors.border }}>
          <div style={{ fontSize: '0.75rem', color: colors.textTertiary, textTransform: 'uppercase' }}>Learned Idle Baseline</div>
          <div style={{ fontSize: '1.8rem', fontWeight: 700, color: colors.accentHover, marginTop: '0.3rem' }}>
            {baseline != null ? `${baseline.toFixed ? baseline.toFixed(1) : baseline} W` : 'learning…'}
          </div>
          <div style={{ fontSize: '0.75rem', color: colors.textTertiary, marginTop: '0.25rem' }}>
            Spread: ±{status?.baseline_spread_w ?? '—'} W (median over baseline window)
          </div>
        </div>

        <div style={{ background: colors.surface, padding: '1.25rem', borderRadius: '0.75rem', border: colors.border }}>
          <div style={{ fontSize: '0.75rem', color: colors.textTertiary, textTransform: 'uppercase' }}>Detection State</div>
          <div style={{ fontSize: '1.4rem', fontWeight: 700, color: colors.amber, marginTop: '0.5rem', textTransform: 'capitalize' }}>
            {String(stateLabel).replace('_', ' ')}
          </div>
          <div style={{ fontSize: '0.75rem', color: colors.textTertiary, marginTop: '0.25rem' }}>
            {status?.active ? 'Monitoring power trace' : 'Watcher inactive'}
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
                : 'Energy unavailable (never reported as zero)'}
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

      {/* Rules Notice */}
      <div style={{ background: colors.surfaceElevated, padding: '1rem', borderRadius: '0.5rem', border: '1px solid rgba(255,255,255,0.08)', fontSize: '0.78rem', color: colors.textTertiary }}>
        <strong style={{ color: colors.textSecondary }}>Honesty Guard (§6b):</strong> Watch observations carry <code>mode="watch"</code> and are strictly excluded from Pareto/selection evidence by default. They inform the budget slider; the actual optimizer selection runs only on verified harness profiling runs.
      </div>
    </div>
  );
};
