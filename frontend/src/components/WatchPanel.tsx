import React, { useEffect, useRef, useState } from 'react';
import { fetchWatchStatus, startWatch, stopWatch } from '../api';
import { WatchStatus } from '../types';
import { fonts, fontFeatures, radii } from '../design';
import { useTheme } from '../ThemeContext';

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
  const { theme, themeColors } = useTheme();
  const c = themeColors;
  const isLight = theme === 'light';

  const [status, setStatus] = useState<WatchStatus | null>(null);
  const [isToggling, setIsToggling] = useState<boolean>(false);
  const [latestSegment, setLatestSegment] = useState<WatchSegmentResult | null>(null);
  const [segmentHistory, setSegmentHistory] = useState<WatchSegmentResult[]>([]);
  const [samples, setSamples] = useState<{ t: string; w: number; inBand: boolean }[]>([]);
  const [liveState, setLiveState] = useState<{
    state: string;
    baseline_median_w: number | null;
    threshold_w?: number | null;
    active_segment_elapsed_s?: number | null;
  } | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const refreshStatus = async () => {
    try {
      const st = await fetchWatchStatus();
      setStatus(st);
    } catch (e) {
      console.error(e);
    }
  };

  // Live SSE: samples, state transitions, closed segments
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
      } catch {
        /* ignore */
      }
    });

    es.addEventListener('watch_state', (ev) => {
      try {
        const data = JSON.parse((ev as MessageEvent).data);
        setLiveState(data);
      } catch {
        /* ignore */
      }
    });

    es.addEventListener('watch_segment', (ev) => {
      try {
        const seg: WatchSegmentResult = JSON.parse((ev as MessageEvent).data);
        setLatestSegment(seg);
        setSegmentHistory((prev) => [seg, ...prev.slice(0, 9)]);
      } catch {
        /* ignore */
      }
    });

    es.onerror = () => es.close();
    return () => es.close();
  }, [status?.active]);

  useEffect(() => {
    refreshStatus();
    const interval = setInterval(refreshStatus, 2500);
    return () => clearInterval(interval);
  }, []);

  const handleToggle = async () => {
    try {
      setIsToggling(true);
      if (status?.active) {
        const res = await stopWatch();
        if (res.segments && res.segments.length > 0) {
          const seg = res.segments[res.segments.length - 1];
          setLatestSegment(seg);
          setSegmentHistory((prev) => [seg, ...prev.slice(0, 9)]);
        }
      } else {
        setSamples([]);
        setLatestSegment(null);
        setLiveState(null);
        await startWatch({ idle_grace_s: 10 });
      }
      await refreshStatus();
    } catch (e: any) {
      alert(`Watch mode error: ${e.message}`);
    } finally {
      setIsToggling(false);
    }
  };

  const isWatching = !!status?.active;
  const stateLabel = liveState?.state ?? status?.state ?? 'idle';
  const power = samples.length > 0 ? samples[samples.length - 1].w : status?.current_power_w;
  const baseline = liveState?.baseline_median_w ?? status?.baseline_median_w;
  const threshold =
    liveState?.threshold_w ??
    status?.threshold_w ??
    (baseline != null
      ? baseline + Math.max(3.0 * (status?.baseline_spread_w ?? 0.5), 0.35 * baseline, 3.5)
      : null);
  const elapsedS = liveState?.active_segment_elapsed_s ?? status?.active_segment_elapsed_s;

  // Mini sparkline of live power
  const renderSparkline = () => {
    if (samples.length < 2) return null;
    const ws = samples.map((s) => s.w);
    const min = Math.min(...ws, 4);
    const max = Math.max(...ws, 25);
    const span = Math.max(max - min, 1);
    const pts = samples
      .map((s, i) => `${(i / (samples.length - 1)) * 100},${36 - ((s.w - min) / span) * 32}`)
      .join(' ');

    return (
      <svg
        viewBox="0 0 100 36"
        preserveAspectRatio="none"
        style={{ width: '100%', height: '48px', marginTop: '8px' }}
      >
        <polyline
          points={pts}
          fill="none"
          stroke={isLight ? '#059669' : '#34d399'}
          strokeWidth="1.5"
        />
      </svg>
    );
  };

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '24px 20px 60px' }}>
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          flexWrap: 'wrap',
          gap: 16,
          marginBottom: 24,
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 24 }}>⏱️</span>
            <h1
              style={{
                fontSize: 22,
                fontWeight: 700,
                color: c.textPrimary,
                margin: 0,
                letterSpacing: '-0.02em',
              }}
            >
              Package Power Watcher & Budget Timer
            </h1>
          </div>
          <p style={{ margin: '6px 0 0', fontSize: 13, color: c.textTertiary, maxWidth: 680 }}>
            Continuously monitors CPU package power for sustained compute spikes (e.g. compilation, rendering, testing).
            When your task finishes, it records the exact duration and calculates your recommended runtime budget.
          </p>
        </div>

        {/* Primary Toggle Action */}
        <button
          onClick={handleToggle}
          disabled={isToggling}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 10,
            background: isWatching
              ? isLight
                ? '#dc2626'
                : '#ef4444'
              : isLight
              ? '#059669'
              : '#10b981',
            color: '#ffffff',
            border: 'none',
            borderRadius: radii.md,
            padding: '10px 20px',
            fontSize: 14,
            fontWeight: 700,
            cursor: isToggling ? 'wait' : 'pointer',
            boxShadow: c.cardShadow,
            transition: 'all 0.15s ease',
          }}
        >
          <span>{isWatching ? '⏹ Stop Watching' : '▶ Start Watching Package Power'}</span>
        </button>
      </div>

      {/* Live Power Metrics Cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: 14,
          marginBottom: 24,
        }}
      >
        {/* Card 1: Live Package Power */}
        <div
          style={{
            background: isLight ? '#ffffff' : c.surface,
            border: `1px solid ${c.border}`,
            borderRadius: radii.lg,
            padding: '18px 20px',
            boxShadow: c.cardShadow,
          }}
        >
          <div style={{ fontSize: 11, fontWeight: 700, color: c.textTertiary, textTransform: 'uppercase' }}>
            Live Package Power
          </div>
          <div
            style={{
              fontSize: 30,
              fontWeight: 700,
              fontFamily: fonts.mono,
              fontFeatureSettings: fontFeatures,
              color: c.textPrimary,
              marginTop: 4,
            }}
          >
            {power != null ? `${power.toFixed(1)} W` : '—'}
          </div>
          {isWatching && renderSparkline()}
          <div style={{ fontSize: 12, color: isWatching ? (isLight ? '#059669' : '#34d399') : c.textTertiary, marginTop: 6 }}>
            {isWatching ? `● Watching Active (${status?.poll_hz ?? 1} Hz)` : '○ Inactive — click start to watch'}
          </div>
        </div>

        {/* Card 2: Rough Idle Baseline & Spike Threshold */}
        <div
          style={{
            background: isLight ? '#ffffff' : c.surface,
            border: `1px solid ${c.border}`,
            borderRadius: radii.lg,
            padding: '18px 20px',
            boxShadow: c.cardShadow,
          }}
        >
          <div style={{ fontSize: 11, fontWeight: 700, color: c.textTertiary, textTransform: 'uppercase' }}>
            Rough Idle Baseline
          </div>
          <div
            style={{
              fontSize: 30,
              fontWeight: 700,
              fontFamily: fonts.mono,
              fontFeatureSettings: fontFeatures,
              color: isLight ? '#4338ca' : '#818cf8',
              marginTop: 4,
            }}
          >
            {baseline != null ? `${baseline.toFixed(1)} W` : isWatching ? 'Observing idle…' : 'Auto-detected'}
          </div>
          <div style={{ fontSize: 12, color: c.textSecondary, marginTop: 8 }}>
            {threshold != null ? (
              <span>
                Spike threshold: <strong>{threshold.toFixed(1)} W</strong>
              </span>
            ) : (
              'Learns idle baseline dynamically on start'
            )}
          </div>
          <div style={{ fontSize: 11, color: c.textTertiary, marginTop: 2 }}>
            Sustained draw above threshold triggers task timing
          </div>
        </div>

        {/* Card 3: Detector State & Elapsed Time */}
        <div
          style={{
            background: isLight ? '#ffffff' : c.surface,
            border: `1px solid ${c.border}`,
            borderRadius: radii.lg,
            padding: '18px 20px',
            boxShadow: c.cardShadow,
          }}
        >
          <div style={{ fontSize: 11, fontWeight: 700, color: c.textTertiary, textTransform: 'uppercase' }}>
            Detector Status
          </div>
          <div
            style={{
              fontSize: 24,
              fontWeight: 700,
              color:
                stateLabel === 'active'
                  ? isLight
                    ? '#d97706'
                    : '#fbbf24'
                  : stateLabel === 'cooldown'
                  ? isLight
                    ? '#2563eb'
                    : '#60a5fa'
                  : c.textPrimary,
              marginTop: 6,
              textTransform: 'capitalize',
            }}
          >
            {stateLabel === 'active'
              ? `⚡ Spike Active (${(elapsedS || 0).toFixed(1)}s)`
              : stateLabel === 'cooldown'
              ? '⏳ Cooldown / Idle Grace'
              : stateLabel === 'learning' || stateLabel === 'calibrating'
              ? '🔍 Observing Idle...'
              : stateLabel === 'idle'
              ? '💤 Idle (Waiting for Task)'
              : stateLabel}
          </div>
          <div style={{ fontSize: 12, color: c.textTertiary, marginTop: 8 }}>
            {stateLabel === 'active'
              ? 'Task compute burst detected! Timing execution duration...'
              : isWatching
              ? 'Run your workload now (e.g. in your terminal or IDE).'
              : 'Standby mode.'}
          </div>
        </div>
      </div>

      {/* Latest Observed Workload Segment (Hero Callout with Apply Button) */}
      {latestSegment && (
        <div
          style={{
            background: isLight ? '#ecfdf5' : 'rgba(16, 185, 129, 0.1)',
            border: `1.5px solid ${isLight ? '#059669' : '#10b981'}`,
            borderRadius: radii.lg,
            padding: '22px 24px',
            marginBottom: 24,
            boxShadow: c.cardShadow,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 16,
          }}
        >
          <div>
            <div
              style={{
                fontSize: 11,
                fontWeight: 700,
                color: isLight ? '#065f46' : '#34d399',
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
              }}
            >
              Workload Power Spike Captured — {latestSegment.segment_id}
            </div>
            <div
              style={{
                fontSize: 20,
                fontWeight: 700,
                color: c.textPrimary,
                marginTop: 4,
              }}
            >
              Observed Duration: <span style={{ fontFamily: fonts.mono }}>{latestSegment.duration_s.toFixed(1)}s</span>
              {latestSegment.estimated_energy_j != null && (
                <span style={{ fontSize: 14, color: c.textSecondary, fontWeight: 500, marginLeft: 12 }}>
                  ({latestSegment.estimated_energy_j.toFixed(0)} J energy)
                </span>
              )}
            </div>
            <div style={{ fontSize: 13, color: isLight ? '#047857' : '#10b981', marginTop: 4, fontWeight: 600 }}>
              Recommended Budget (+20% slack): <strong>{latestSegment.suggested_budget_s.toFixed(1)}s</strong>
            </div>
          </div>

          <button
            onClick={() => onApplySuggestedBudget(latestSegment.suggested_budget_s, latestSegment.duration_s)}
            style={{
              background: isLight ? '#059669' : '#10b981',
              color: '#ffffff',
              border: 'none',
              borderRadius: radii.md,
              padding: '11px 22px',
              fontSize: 14,
              fontWeight: 700,
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
            }}
          >
            <span>Apply to Setup Budget ({latestSegment.suggested_budget_s.toFixed(1)}s)</span>
            <span>→</span>
          </button>
        </div>
      )}

      {/* How to Time Your Budget Step-by-Step Card */}
      <div
        style={{
          background: isLight ? '#ffffff' : c.surface,
          border: `1px solid ${c.border}`,
          borderRadius: radii.lg,
          padding: '22px 24px',
          marginBottom: 24,
          boxShadow: c.cardShadow,
        }}
      >
        <h3 style={{ margin: '0 0 12px', fontSize: 15, fontWeight: 700, color: c.textPrimary }}>
          How to Time Your Workload Budget
        </h3>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: 14,
          }}
        >
          <div
            style={{
              background: isLight ? '#f8fafc' : 'rgba(255, 255, 255, 0.02)',
              border: `1px solid ${c.borderSubtle}`,
              borderRadius: radii.md,
              padding: '14px',
            }}
          >
            <div style={{ fontWeight: 700, fontSize: 13, color: c.textPrimary, marginBottom: 4 }}>
              1. Start Watching
            </div>
            <div style={{ fontSize: 12, color: c.textSecondary, lineHeight: 1.5 }}>
              Click <strong>Start Watching</strong> above. Joulectrl instantly observes your machine's idle baseline power (~6–8 W).
            </div>
          </div>

          <div
            style={{
              background: isLight ? '#f8fafc' : 'rgba(255, 255, 255, 0.02)',
              border: `1px solid ${c.borderSubtle}`,
              borderRadius: radii.md,
              padding: '14px',
            }}
          >
            <div style={{ fontWeight: 700, fontSize: 13, color: c.textPrimary, marginBottom: 4 }}>
              2. Run Your Task
            </div>
            <div style={{ fontSize: 12, color: c.textSecondary, lineHeight: 1.5 }}>
              Run your build, test suite, or render in your terminal or editor (e.g. <code>cargo build</code>, <code>make</code>, or Blender).
            </div>
          </div>

          <div
            style={{
              background: isLight ? '#f8fafc' : 'rgba(255, 255, 255, 0.02)',
              border: `1px solid ${c.borderSubtle}`,
              borderRadius: radii.md,
              padding: '14px',
            }}
          >
            <div style={{ fontWeight: 700, fontSize: 13, color: c.textPrimary, marginBottom: 4 }}>
              3. Automatic Spike Timing
            </div>
            <div style={{ fontSize: 12, color: c.textSecondary, lineHeight: 1.5 }}>
              When package power spikes above idle, the timer starts. When your task ends and power drops, the timer closes the window.
            </div>
          </div>

          <div
            style={{
              background: isLight ? '#f8fafc' : 'rgba(255, 255, 255, 0.02)',
              border: `1px solid ${c.borderSubtle}`,
              borderRadius: radii.md,
              padding: '14px',
            }}
          >
            <div style={{ fontWeight: 700, fontSize: 13, color: c.textPrimary, marginBottom: 4 }}>
              4. Apply Recommended Budget
            </div>
            <div style={{ fontSize: 12, color: c.textSecondary, lineHeight: 1.5 }}>
              Click <strong>Apply to Setup Budget</strong>. Joulectrl transfers your measured task duration and +20% slack into the optimizer.
            </div>
          </div>
        </div>
      </div>

      {/* Historical Observed Segments Table */}
      {segmentHistory.length > 0 && (
        <div
          style={{
            background: isLight ? '#ffffff' : c.surface,
            border: `1px solid ${c.border}`,
            borderRadius: radii.lg,
            padding: '20px 22px',
            boxShadow: c.cardShadow,
          }}
        >
          <h3 style={{ margin: '0 0 14px', fontSize: 15, fontWeight: 700, color: c.textPrimary }}>
            Recently Observed Workload Bursts
          </h3>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${c.border}`, color: c.textTertiary, textAlign: 'left' }}>
                <th style={{ padding: '8px 6px', fontWeight: 600 }}>SEGMENT ID</th>
                <th style={{ padding: '8px 6px', fontWeight: 600 }}>OBSERVED DURATION</th>
                <th style={{ padding: '8px 6px', fontWeight: 600 }}>ENERGY</th>
                <th style={{ padding: '8px 6px', fontWeight: 600 }}>SUGGESTED BUDGET (+20%)</th>
                <th style={{ padding: '8px 6px', fontWeight: 600 }}>ACTION</th>
              </tr>
            </thead>
            <tbody>
              {segmentHistory.map((seg) => (
                <tr key={seg.segment_id} style={{ borderBottom: `1px solid ${c.borderSubtle}`, color: c.textPrimary }}>
                  <td style={{ padding: '10px 6px', fontFamily: fonts.mono }}>{seg.segment_id}</td>
                  <td style={{ padding: '10px 6px', fontFamily: fonts.mono, fontWeight: 700 }}>
                    {seg.duration_s.toFixed(1)}s
                  </td>
                  <td style={{ padding: '10px 6px', fontFamily: fonts.mono, color: c.textSecondary }}>
                    {seg.estimated_energy_j != null ? `${seg.estimated_energy_j.toFixed(0)} J` : '—'}
                  </td>
                  <td style={{ padding: '10px 6px', fontFamily: fonts.mono, color: isLight ? '#059669' : '#34d399', fontWeight: 700 }}>
                    {seg.suggested_budget_s.toFixed(1)}s
                  </td>
                  <td style={{ padding: '10px 6px' }}>
                    <button
                      onClick={() => onApplySuggestedBudget(seg.suggested_budget_s, seg.duration_s)}
                      style={{
                        padding: '4px 10px',
                        borderRadius: radii.sm,
                        background: isLight ? '#eff6ff' : 'rgba(99, 102, 241, 0.15)',
                        border: `1px solid ${isLight ? '#bfdbfe' : 'rgba(99, 102, 241, 0.4)'}`,
                        color: isLight ? '#1d4ed8' : '#818cf8',
                        fontSize: 11,
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      Apply
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
