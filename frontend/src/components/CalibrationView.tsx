import React, { useEffect, useMemo, useState, useCallback } from 'react';
import {
  fetchCalibration,
  fetchCalibrationStatus,
  startCalibration,
  stopCalibration,
  CalibrationTier,
  CalibrationStatusResponse,
  fetchSystemNoise,
  quietSystem,
  SystemNoiseStatus,
  setFocusSwitch,
  setProcessPriority,
} from '../api';
import { colors, fonts, fontFeatures, type, radii, card, sectionLabel } from '../design';

/* ------------------------------------------------------------------ */
/* data types                                                          */
/* ------------------------------------------------------------------ */

interface CalPoint {
  control: string;
  config_id?: string;
  workers: number;
  cpus: number[];
  scope: 'single' | 'multi';
  runtime_s: number;
  energy_j: number;
  watts: number;
  perfPerWatt: number;
  perf_per_watt?: number;
  throughput: number;
  score?: number;
  series?: string;
  n?: number;
  scalingEfficiency?: number | null;
  scaling_efficiency?: number | null;
}

interface ClassSummary {
  label: string;
  hw_max_freq_khz?: number | null;
  c1?: { runtime_s: number; energy_j: number; cpus?: number[] } | null;
  points: CalPoint[];
}

interface CalibrationExperiment {
  id: string;
  title?: string;
  workload_name?: string;
  run_count: number;
  created_at?: string;
}

interface CalibrationData {
  source: string;
  captured_utc?: string;
  kernel?: string;
  topology?: { physical_cores?: number; logical_cores?: number };
  classes: ClassSummary[];
  scopes_available?: Record<string, string[]>;
  all_cores_measured?: boolean;
  workers_available?: number[];
  experiments?: CalibrationExperiment[];
  current_experiment_id?: string;
  total_runs_aggregated?: number;
  note?: string;
}

type ClassFilter = 'all' | 'combined' | string;
type ScopeFilter = 'all' | 'single' | 'multi';

/* ------------------------------------------------------------------ */
/* helpers                                                             */
/* ------------------------------------------------------------------ */

const fmt = (v: number | undefined | null, digits = 1) =>
  v == null || Number.isNaN(v as number) ? '—' : (v as number).toFixed(digits);

const classColor = (label: string) =>
  label === 'fast'
    ? colors.series.fast
    : label === 'efficient'
      ? colors.series.efficient
      : label === 'all_physical'
        ? '#38bdf8'
        : '#60a5fa';

/** Data-driven class display name: "fast · ≤5.09 GHz" — never hardcoded core names. */
const classDisplayName = (c: ClassSummary) => {
  if (c.label === 'all' || c.label === 'all_logical') return 'all cores · 16 threads (SMT)';
  if (c.label === 'all_physical') return 'all physical · 8 cores';
  return c.hw_max_freq_khz ? `${c.label} · ≤${(c.hw_max_freq_khz / 1e6).toFixed(2)} GHz` : c.label;
};

const SERIES_PALETTE: Record<string, string> = {
  'Zen 5 (1 cores)': '#818cf8',
  'Zen 5 (4 cores)': '#a78bfa',
  'Zen 5 (8 threads)': '#c084fc',
  'Zen 5c (1 cores)': '#6ee7b7',
  'Zen 5c (4 cores)': '#34d399',
  'Zen 5c (8 threads)': '#10b981',
  'All Physical (8 cores)': '#38bdf8',
  'All Cores (8 threads)': '#38bdf8',
  'All Cores (16 threads)': '#60a5fa',
  'fast': colors.series.fast,
  'efficient': colors.series.efficient,
  'all': '#60a5fa',
  'all_logical': '#60a5fa',
  'all_physical': '#38bdf8',
};

/* ------------------------------------------------------------------ */
/* chart primitives (SVG)                                              */
/* ------------------------------------------------------------------ */

interface Point {
  x: number;
  y: number;
  label: string;
  series?: string;
  subSeries?: string;
  color?: string;
  meta?: Record<string, string | number>;
}

function ScatterChart({
  points,
  series,
  seriesKey,
  xLabel,
  yLabel,
  xUnit,
  yUnit,
  height = 280,
  onHover,
  connectSeries = true,
  showPareto = true,
}: {
  points: Point[];
  series: Record<string, string>;
  seriesKey: (p: Point) => string;
  connectSeries?: boolean;
  showPareto?: boolean;
  xLabel: string;
  yLabel: string;
  xUnit?: string;
  yUnit?: string;
  height?: number;
  onHover?: (p: Point | null) => void;
}) {
  const W = 620;
  const H = height;
  const M = { top: 16, right: 24, bottom: 44, left: 60 };
  const iw = W - M.left - M.right;
  const ih = H - M.top - M.bottom;

  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  if (xs.length === 0) return null;
  const xMin = Math.max(0, Math.min(...xs) * 0.85);
  const xMax = Math.max(...xs) * 1.08;
  const yMin = 0;
  const yMax = Math.max(...ys) * 1.1;
  const xPad = (xMax - xMin) * 0.05 || 1;
  const yPad = (yMax - yMin) * 0.05 || 1;

  const sx = (v: number) => M.left + ((v - (xMin - xPad * 0.5)) / (xMax - xMin + xPad)) * iw;
  const sy = (v: number) => H - M.bottom - ((v - yMin) / (yMax - yMin + yPad * 0.1)) * ih;

  const ticksY = 4;
  const tickVals = Array.from({ length: ticksY + 1 }, (_, i) => yMin + ((yMax - yMin) * i) / ticksY);
  const ticksX = 4;
  const xTickVals = Array.from({ length: ticksX + 1 }, (_, i) => xMin + ((xMax - xMin) * i) / ticksX);

  // Group points by subSeries for monotonic curve lines (never zig-zag)
  const groupedSubSeries = useMemo(() => {
    const acc: Record<string, Point[]> = {};
    for (const p of points) {
      const k = p.subSeries || seriesKey(p);
      (acc[k] ||= []).push(p);
    }
    for (const k in acc) {
      acc[k].sort((a, b) => a.x - b.x);
    }
    return acc;
  }, [points, seriesKey]);

  // Compute Pareto Optimal Frontier per sub-series (same worker count / topology)
  // Never connect points across different thread counts (e.g. 8w vs 16w)
  const paretoFrontiers = useMemo(() => {
    const acc: Record<string, Point[]> = {};
    for (const p of points) {
      const k = p.subSeries || seriesKey(p);
      (acc[k] ||= []).push(p);
    }
    const list: { key: string; points: Point[]; color: string }[] = [];
    for (const [k, pts] of Object.entries(acc)) {
      const sorted = [...pts].sort((a, b) => a.x - b.x);
      const frontier: Point[] = [];
      let maxY = -Infinity;
      for (const p of sorted) {
        if (p.y > maxY) {
          frontier.push(p);
          maxY = p.y;
        }
      }
      if (frontier.length >= 2) {
        list.push({
          key: k,
          points: frontier,
          color: SERIES_PALETTE[k] || '#22d3ee',
        });
      }
    }
    return list;
  }, [points, seriesKey]);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto', display: 'block' }}>
      {/* Horizontal grid lines & Y ticks */}
      {tickVals.map((v, i) => (
        <g key={i}>
          <line x1={M.left} x2={W - M.right} y1={sy(v)} y2={sy(v)} stroke={colors.borderSubtle} strokeWidth={1} />
          <text x={M.left - 8} y={sy(v) + 3.5} textAnchor="end" fontSize={10} fill={colors.textQuaternary} fontFamily={fonts.mono}>
            {v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(v < 10 ? 1 : 0)}
          </text>
        </g>
      ))}

      {/* Vertical grid lines & X ticks */}
      {xTickVals.map((v, i) => (
        <g key={i}>
          <line x1={sx(v)} x2={sx(v)} y1={M.top} y2={H - M.bottom} stroke={colors.borderSubtle} strokeWidth={0.5} strokeDasharray="2 4" />
          <text x={sx(v)} y={H - M.bottom + 14} textAnchor="middle" fontSize={10} fill={colors.textQuaternary} fontFamily={fonts.mono}>
            {v.toFixed(v < 10 ? 1 : 0)}
          </text>
        </g>
      ))}

      {/* Axis Labels */}
      <text x={M.left + iw / 2} y={H - 6} textAnchor="middle" fontSize={11} fill={colors.textTertiary}>
        {xLabel}{xUnit ? ` (${xUnit})` : ''}
      </text>
      <text
        x={12}
        y={M.top + ih / 2}
        textAnchor="middle"
        fontSize={11}
        fill={colors.textTertiary}
        transform={`rotate(-90 12 ${M.top + ih / 2})`}
      >
        {yLabel}{yUnit ? ` (${yUnit})` : ''}
      </text>

      {/* Pareto frontier curves per series (never crossing thread counts) */}
      {showPareto &&
        paretoFrontiers.map((f) => (
          <g key={`pareto-${f.key}`}>
            <path
              d={f.points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${sx(p.x)} ${sy(p.y)}`).join(' ')}
              fill="none"
              stroke="#22d3ee"
              strokeWidth={2}
              strokeDasharray="5 3"
              opacity={0.85}
              pointerEvents="none"
            />
          </g>
        ))}

      {/* Per-series curves: sorted by wattage ascending, monotonic curves that never zig-zag */}
      {connectSeries &&
        Object.entries(groupedSubSeries).map(([k, pts]) => {
          const sorted = [...pts].sort((a, b) => a.x - b.x);
          if (sorted.length < 2) return null;
          const d = sorted.map((p, i) => `${i === 0 ? 'M' : 'L'} ${sx(p.x)} ${sy(p.y)}`).join(' ');
          const col = SERIES_PALETTE[k] || series[pts[0].series ?? ''] || colors.series.accent2;
          return (
            <path
              key={`line-${k}`}
              d={d}
              fill="none"
              stroke={col}
              strokeWidth={2}
              opacity={0.7}
              pointerEvents="none"
            />
          );
        })}

      {/* Data point markers */}
      {points.map((p, i) => {
        const col = p.color || SERIES_PALETTE[p.subSeries || ''] || series[p.series ?? ''] || colors.series.accent2;
        return (
          <g key={i} style={{ cursor: onHover ? 'pointer' : 'default' }}>
            <circle
              cx={sx(p.x)}
              cy={sy(p.y)}
              r={12}
              fill="transparent"
              onMouseEnter={() => onHover?.(p)}
              onMouseLeave={() => onHover?.(null)}
            />
            <circle
              cx={sx(p.x)}
              cy={sy(p.y)}
              r={4.5}
              fill={col}
              stroke={colors.bg}
              strokeWidth={1.5}
              pointerEvents="none"
            />
          </g>
        );
      })}
    </svg>
  );
}

/* small pill toggle used by pickers */
const Picker: React.FC<{
  options: { key: string; label: string; disabled?: boolean; color?: string }[];
  value: string;
  onChange: (v: string) => void;
}> = ({ options, value, onChange }) => (
  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
    {options.map((o) => {
      const on = value === o.key;
      const col = o.color ?? colors.accent;
      return (
        <button
          key={o.key}
          disabled={o.disabled}
          onClick={() => onChange(o.key)}
          style={{
            ...type.smallMedium,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '4px 12px',
            borderRadius: radii.full,
            border: `1px solid ${on ? col : colors.border}`,
            background: on ? `${col}14` : 'transparent',
            color: on ? colors.textPrimary : colors.textTertiary,
            cursor: o.disabled ? 'not-allowed' : 'pointer',
            opacity: o.disabled ? 0.4 : 1,
            font: 'inherit',
            fontSize: 12,
          }}
        >
          {o.color && <span style={{ width: 7, height: 7, borderRadius: '50%', background: on ? o.color : colors.textQuaternary }} />}
          {o.label}
        </button>
      );
    })}
  </div>
);

/* ------------------------------------------------------------------ */
/* main view                                                           */
/* ------------------------------------------------------------------ */

export const CalibrationView: React.FC = () => {
  const [data, setData] = useState<CalibrationData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [classFilter, setClassFilter] = useState<ClassFilter>('all');
  const [scopeFilter, setScopeFilter] = useState<ScopeFilter>('all');
  const [selectedExpId, setSelectedExpId] = useState<string>('');
  const [showPareto, setShowPareto] = useState<boolean>(true);
  const [hovered, setHovered] = useState<Point | null>(null);

  // Calibration Runner state
  const [calibrationStatus, setCalibrationStatus] = useState<CalibrationStatusResponse | null>(null);
  const [selectedTier, setSelectedTier] = useState<CalibrationTier>('quick');
  const [showNoiseModal, setShowNoiseModal] = useState<boolean>(false);
  const [noiseStatus, setNoiseStatus] = useState<SystemNoiseStatus | null>(null);
  const [isQuieting, setIsQuieting] = useState<boolean>(false);
  const [selectedAppsToQuiet, setSelectedAppsToQuiet] = useState<Record<string, boolean>>({});
  const [isStartingSweep, setIsStartingSweep] = useState<boolean>(false);
  const [isStoppingSweep, setIsStoppingSweep] = useState<boolean>(false);
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);

  const formatSeconds = (s: number | undefined | null) => {
    if (s == null || s <= 0 || Number.isNaN(s)) return '0s';
    const m = Math.floor(s / 60);
    const rem = Math.round(s % 60);
    if (m === 0) return `${rem}s`;
    return `${m}m ${rem}s`;
  };

  useEffect(() => {
    fetchCalibration(selectedExpId || undefined)
      .then(setData)
      .catch((e) => setError(String(e?.message ?? e)));
  }, [selectedExpId]);

  useEffect(() => {
    fetchCalibrationStatus()
      .then(setCalibrationStatus)
      .catch(() => {});

    const ev = new EventSource('/api/calibration/events');
    ev.addEventListener('calibration_progress', (e: MessageEvent) => {
      try {
        const d = JSON.parse(e.data);
        setCalibrationStatus({
          is_running: true,
          session_id: d.session_id,
          tier: d.tier,
          tier_name: d.tier === 'quick' ? 'Quick Tier (~20m)' : d.tier === 'standard' ? 'Standard Tier (~1h)' : 'Exhaustive Tier (3x per freq)',
          current_step: d.current_step,
          total_steps: d.total_steps,
          percent: d.percent,
          elapsed_s: d.elapsed_s,
          eta_s: d.eta_s,
          status_message: `Measuring ${d.class_display} @ ${d.freq_label} (Rep ${d.rep}/${d.reps_total})`,
          latest_point: d.latest_point,
          points_count: d.current_step,
        });
      } catch (err) {}
    });

    ev.addEventListener('calibration_complete', () => {
      fetchCalibrationStatus().then(setCalibrationStatus).catch(() => {});
      fetchCalibration(selectedExpId || undefined).then(setData).catch(() => {});
      setActionFeedback('✓ Calibration complete! All measured points plotted on the curve.');
      setTimeout(() => setActionFeedback(null), 5000);
    });

    ev.addEventListener('calibration_cancelled', () => {
      fetchCalibrationStatus().then(setCalibrationStatus).catch(() => {});
      fetchCalibration(selectedExpId || undefined).then(setData).catch(() => {});
      setActionFeedback('✓ Calibration stopped safely. Hardware restored to stock.');
      setTimeout(() => setActionFeedback(null), 5000);
    });

    return () => ev.close();
  }, [selectedExpId]);

  const classes = data?.classes ?? [];
  const visibleClasses =
    classFilter === 'all' || classFilter === 'combined'
      ? classes
      : classes.filter((c) => c.label === classFilter);

  const filteredPointsByClass = useMemo(() => {
    const m = new Map<string, CalPoint[]>();
    for (const c of visibleClasses) {
      m.set(
        c.label,
        c.points.filter((p) => {
          if (scopeFilter === 'all') return true;
          if (scopeFilter === 'single') return p.scope === 'single';
          return p.scope === 'multi';
        }),
      );
    }
    return m;
  }, [visibleClasses, scopeFilter]);

  const seriesColors = useMemo(() => {
    const m: Record<string, string> = {};
    for (const c of classes) m[c.label] = classColor(c.label);
    return m;
  }, [classes]);

  const scopeOptions: { key: ScopeFilter; label: string; disabled?: boolean }[] = [
    { key: 'all', label: 'All scopes' },
    { key: 'single', label: 'Single-core' },
    { key: 'multi', label: `Multicore${data?.workers_available?.length ? ` (${data.workers_available.filter((w) => w > 1).join('/')} workers)` : ''}` },
  ];

  const handleCheckNoiseAndStart = async () => {
    try {
      setIsStartingSweep(true);
      const noise = await fetchSystemNoise();
      setNoiseStatus(noise);
      if (noise.detected_apps.length > 0) {
        const appMap: Record<string, boolean> = {};
        for (const app of noise.detected_apps) appMap[app.key] = true;
        setSelectedAppsToQuiet(appMap);
        setShowNoiseModal(true);
      } else {
        await executeStartCalibration(false);
      }
    } catch (e: any) {
      await executeStartCalibration(false);
    } finally {
      setIsStartingSweep(false);
    }
  };

  const executeStartCalibration = async (quiet: boolean = false) => {
    try {
      setIsStartingSweep(true);
      await startCalibration({
        tier: selectedTier,
        quiet_background: quiet,
      });
      setShowNoiseModal(false);
      const st = await fetchCalibrationStatus();
      setCalibrationStatus(st);
      setActionFeedback(`⚡ Started ${selectedTier} calibration sweep! Measurements are streaming live.`);
      setTimeout(() => setActionFeedback(null), 5000);
    } catch (e: any) {
      setActionFeedback(`⚠️ Calibration error: ${e?.message ?? e}`);
      setTimeout(() => setActionFeedback(null), 6000);
    } finally {
      setIsStartingSweep(false);
    }
  };

  const handleStopCalibration = async () => {
    try {
      setIsStoppingSweep(true);
      const res = await stopCalibration();
      setActionFeedback(`✓ ${res.message} (Saved ${res.points_saved} points)`);
      setTimeout(() => setActionFeedback(null), 5000);
      const st = await fetchCalibrationStatus();
      setCalibrationStatus(st);
      const cal = await fetchCalibration(selectedExpId || undefined);
      setData(cal);
    } catch (e: any) {
      setActionFeedback(`⚠️ Stop error: ${e?.message ?? e}`);
      setTimeout(() => setActionFeedback(null), 5000);
    } finally {
      setIsStoppingSweep(false);
    }
  };

  const handleQuietApps = async () => {
    try {
      setIsQuieting(true);
      const keysToQuiet = Object.entries(selectedAppsToQuiet)
        .filter(([_, sel]) => sel)
        .map(([k]) => k);
      await quietSystem(keysToQuiet.length > 0 ? keysToQuiet : undefined);
      await executeStartCalibration(true);
    } catch (e: any) {
      setActionFeedback(`⚠️ Quieting error: ${e?.message ?? e}`);
      setTimeout(() => setActionFeedback(null), 5000);
      await executeStartCalibration(false);
    } finally {
      setIsQuieting(false);
      setShowNoiseModal(false);
    }
  };

  const handleApplyPreferencePreset = async (preset: 'performance' | 'sweetspot' | 'powersave') => {
    try {
      if (preset === 'performance') {
        await setFocusSwitch({ mode: 'on' });
        setActionFeedback('✓ Preference applied: Max Performance (Boost ON, Fast cores shielded)');
      } else if (preset === 'powersave') {
        await setFocusSwitch({ mode: 'reverse' });
        setActionFeedback('✓ Preference applied: Maximum Power-Saving (Pinned to Zen 5c Eco cores, Nice +15)');
      } else {
        await setFocusSwitch({ mode: 'off' });
        setActionFeedback('✓ Preference applied: Balanced Sweet Spot (All cores, Pareto-optimal scheduling)');
      }
      setTimeout(() => setActionFeedback(null), 4500);
    } catch (e: any) {
      setActionFeedback(`⚠️ Preference error: ${e?.message ?? e}`);
      setTimeout(() => setActionFeedback(null), 5000);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 1160, margin: '0 auto', fontFamily: fonts.sans, fontFeatureSettings: fontFeatures }}>
      {/* header + controls */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <div style={{ ...type.display, color: colors.textPrimary }}>Calibration</div>
          <div style={{ ...type.small, color: colors.textTertiary, marginTop: 4 }}>
            Measured performance vs power curves across core classes and frequencies.
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-end' }}>
          {/* Experiment selector dropdown if experiments exist */}
          {data?.experiments && data.experiments.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ ...type.micro, color: colors.textQuaternary, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Dataset</span>
              <select
                value={selectedExpId || data.current_experiment_id || ''}
                onChange={(e) => setSelectedExpId(e.target.value)}
                style={{
                  background: colors.surfaceElevated,
                  color: colors.textPrimary,
                  border: `1px solid ${colors.border}`,
                  borderRadius: radii.sm,
                  padding: '4px 10px',
                  fontFamily: fonts.sans,
                  fontSize: 12,
                  outline: 'none',
                  cursor: 'pointer',
                }}
              >
                <option value="all">All Experiments (Combined)</option>
                {data.experiments.map((exp) => (
                  <option key={exp.id} value={exp.id}>
                    {exp.workload_name || exp.id} ({exp.run_count} runs)
                  </option>
                ))}
              </select>
            </div>
          )}

          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ ...type.micro, color: colors.textQuaternary, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Cores</span>
            <Picker
              options={[
                { key: 'all', label: 'All classes' },
                ...classes.map((c) => ({ key: c.label, label: classDisplayName(c), color: classColor(c.label) })),
                { key: 'combined', label: 'Combined overlay' },
              ]}
              value={classFilter}
              onChange={(v) => setClassFilter(v)}
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ ...type.micro, color: colors.textQuaternary, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Scope</span>
            <Picker options={scopeOptions} value={scopeFilter} onChange={(v) => setScopeFilter(v as ScopeFilter)} />
          </div>
        </div>
      </div>

      {actionFeedback && (
        <div
          style={{
            ...card,
            padding: '10px 16px',
            background: 'rgba(16, 185, 129, 0.12)',
            border: '1px solid rgba(16, 185, 129, 0.35)',
            color: colors.emerald,
            fontSize: 13,
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <span>{actionFeedback}</span>
        </div>
      )}

      {/* Multithreaded Frequency Calibration Suite */}
      <div
        style={{
          ...card,
          padding: 20,
          background: calibrationStatus?.is_running
            ? 'linear-gradient(135deg, rgba(34, 211, 238, 0.08) 0%, rgba(16, 185, 129, 0.06) 100%)'
            : colors.surface,
          border: `1px solid ${calibrationStatus?.is_running ? 'rgba(34, 211, 238, 0.4)' : colors.border}`,
          boxShadow: calibrationStatus?.is_running ? '0 0 24px rgba(34, 211, 238, 0.12)' : colors.cardShadow,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: 16, fontWeight: 700, color: colors.textPrimary }}>
                Multithreaded Frequency Calibration Suite
              </span>
              <span
                style={{
                  fontSize: 11,
                  fontFamily: fonts.mono,
                  padding: '2px 8px',
                  borderRadius: radii.full,
                  background: 'rgba(99, 102, 241, 0.15)',
                  border: '1px solid rgba(99, 102, 241, 0.3)',
                  color: '#a5b4fc',
                }}
              >
                3 Core Classes (All 16w · Zen 5 Fast 8w · Zen 5c Eco 8w)
              </span>
            </div>
            <div style={{ fontSize: 12, color: colors.textTertiary, marginTop: 4, maxWidth: 680 }}>
              Profiles continuous hardware frequencies across the 3 multithreaded core classes to map real empirical throughput vs package power curves for Pareto optimization.
            </div>
          </div>

          {calibrationStatus?.is_running ? (
            <button
              onClick={handleStopCalibration}
              disabled={isStoppingSweep}
              style={{
                padding: '7px 16px',
                borderRadius: radii.md,
                background: '#ef4444',
                border: 'none',
                color: '#fff',
                fontSize: 12,
                fontWeight: 700,
                cursor: isStoppingSweep ? 'wait' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                boxShadow: '0 2px 8px rgba(239, 68, 68, 0.4)',
              }}
            >
              <span>⏹</span> {isStoppingSweep ? 'Restoring Hardware...' : 'Stop Calibration'}
            </button>
          ) : (
            <button
              onClick={handleCheckNoiseAndStart}
              disabled={isStartingSweep}
              style={{
                padding: '7px 18px',
                borderRadius: radii.md,
                background: colors.accentBg,
                border: 'none',
                color: '#fff',
                fontSize: 12,
                fontWeight: 700,
                cursor: isStartingSweep ? 'wait' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                boxShadow: '0 2px 10px rgba(99, 102, 241, 0.4)',
              }}
            >
              <span>🚀</span> {isStartingSweep ? 'Starting...' : `Start ${selectedTier.toUpperCase()} Sweep`}
            </button>
          )}
        </div>

        {/* Active Running State */}
        {calibrationStatus?.is_running ? (
          <div style={{ marginTop: 16, background: 'rgba(0,0,0,0.25)', borderRadius: radii.md, padding: 14, border: '1px solid rgba(34, 211, 238, 0.2)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10, marginBottom: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 9, height: 9, borderRadius: '50%', background: '#22d3ee', boxShadow: '0 0 8px #22d3ee' }} />
                <span style={{ fontSize: 13, fontWeight: 700, color: '#22d3ee' }}>
                  {calibrationStatus.status_message}
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 14, fontSize: 12, fontFamily: fonts.mono }}>
                <span style={{ color: colors.textSecondary }}>
                  Step <strong>{calibrationStatus.current_step}</strong> / {calibrationStatus.total_steps} ({calibrationStatus.percent}%)
                </span>
                <span style={{ color: colors.textTertiary }}>
                  Elapsed: <strong>{formatSeconds(calibrationStatus.elapsed_s)}</strong>
                </span>
                <span style={{ color: '#22d3ee' }}>
                  ETA: <strong>~{formatSeconds(calibrationStatus.eta_s)}</strong>
                </span>
              </div>
            </div>

            {/* Progress bar */}
            <div style={{ width: '100%', height: 7, borderRadius: radii.full, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}>
              <div
                style={{
                  width: `${calibrationStatus.percent}%`,
                  height: '100%',
                  borderRadius: radii.full,
                  background: 'linear-gradient(90deg, #6366f1 0%, #22d3ee 50%, #10b981 100%)',
                  transition: 'width 0.3s ease',
                  boxShadow: '0 0 10px rgba(34, 211, 238, 0.5)',
                }}
              />
            </div>
          </div>
        ) : (
          /* Tier Selection Cards */
          <div style={{ marginTop: 14 }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 10 }}>
              {[
                {
                  id: 'quick' as CalibrationTier,
                  title: '⚡ Quick Tier',
                  estTime: '~20 mins',
                  desc: '4 frequency points per class · 1 rep · Fast curve outline for immediate optimization.',
                  badge: 'Rapid Outline',
                },
                {
                  id: 'standard' as CalibrationTier,
                  title: '⚖️ Standard Tier',
                  estTime: '~50–60 mins',
                  desc: '7 frequency points per class · 2 reps · Median noise-filtered Pareto frontier.',
                  badge: 'Recommended',
                },
                {
                  id: 'exhaustive' as CalibrationTier,
                  title: '🔬 Exhaustive (3x Reps)',
                  estTime: 'Thorough pass',
                  desc: '10 fine frequencies per class · 3 full reps · Maximum statistical confidence.',
                  badge: 'Full Precision',
                },
              ].map((tier) => {
                const isSelected = selectedTier === tier.id;
                return (
                  <div
                    key={tier.id}
                    onClick={() => setSelectedTier(tier.id)}
                    style={{
                      padding: 12,
                      borderRadius: radii.md,
                      background: isSelected ? 'rgba(99, 102, 241, 0.12)' : 'rgba(255, 255, 255, 0.02)',
                      border: `1.5px solid ${isSelected ? '#818cf8' : colors.border}`,
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 6,
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: 13, fontWeight: 700, color: isSelected ? '#818cf8' : colors.textPrimary }}>
                        {tier.title}
                      </span>
                      <span
                        style={{
                          fontSize: 10,
                          fontWeight: 600,
                          padding: '1px 6px',
                          borderRadius: radii.full,
                          background: isSelected ? 'rgba(129, 140, 248, 0.25)' : 'rgba(255,255,255,0.06)',
                          color: isSelected ? '#818cf8' : colors.textTertiary,
                        }}
                      >
                        {tier.estTime}
                      </span>
                    </div>
                    <div style={{ fontSize: 11, color: colors.textSecondary, lineHeight: 1.4 }}>
                      {tier.desc}
                    </div>
                  </div>
                );
              })}
            </div>
            <div style={{ fontSize: 11, color: colors.textTertiary, marginTop: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
              <span>🛡️ Pre-flight noise detection ensures background apps (browsers, Discord, games) do not distort the calibration measurements.</span>
            </div>
          </div>
        )}
      </div>

      {/* Preference Mode Sweet Spot Selection Bar */}
      <div style={{ ...card, padding: 14, background: 'rgba(255,255,255,0.02)', border: `1px solid ${colors.borderSubtle}` }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 13, fontWeight: 700, color: colors.textPrimary }}>
                🎯 Preference Mode Presets
              </span>
              <span style={{ fontSize: 11, color: colors.textTertiary }}>
                Operating points selected directly from the empirical multithreaded curves
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button
              onClick={() => handleApplyPreferencePreset('performance')}
              style={{
                padding: '4px 12px',
                borderRadius: radii.sm,
                border: '1px solid rgba(129, 140, 248, 0.4)',
                background: 'rgba(129, 140, 248, 0.12)',
                color: '#818cf8',
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              🚀 Max Performance (Boost ON)
            </button>
            <button
              onClick={() => handleApplyPreferencePreset('sweetspot')}
              style={{
                padding: '4px 12px',
                borderRadius: radii.sm,
                border: '1px solid rgba(34, 211, 238, 0.4)',
                background: 'rgba(34, 211, 238, 0.12)',
                color: '#22d3ee',
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              🎯 Pareto Sweet Spot (70% Power / 90% Perf)
            </button>
            <button
              onClick={() => handleApplyPreferencePreset('powersave')}
              style={{
                padding: '4px 12px',
                borderRadius: radii.sm,
                border: '1px solid rgba(16, 185, 129, 0.4)',
                background: 'rgba(16, 185, 129, 0.12)',
                color: '#10b981',
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              🍃 Max Power-Saving (Zen 5c Eco)
            </button>
          </div>
        </div>
      </div>

      {/* Noise Modal */}
      {showNoiseModal && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.7)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
          }}
        >
          <div
            style={{
              background: colors.surface,
              borderRadius: radii.lg,
              border: `1px solid ${colors.border}`,
              padding: 24,
              maxWidth: 500,
              width: '90%',
              boxShadow: '0 20px 40px rgba(0,0,0,0.6)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
              <span style={{ fontSize: 24 }}>🧹</span>
              <h3 style={{ margin: 0, fontSize: 16, color: colors.textPrimary }}>Clean Calibration Environment</h3>
            </div>
            <p style={{ fontSize: 13, color: colors.textSecondary, lineHeight: 1.5, marginBottom: 16 }}>
              Accurate calibration requires an undisturbed CPU. Background processes (browsers, Discord, Steam) create power spikes and skew measured clock scaling.
            </p>

            {noiseStatus?.detected_apps && noiseStatus.detected_apps.length > 0 ? (
              <div style={{ marginBottom: 16, background: 'rgba(255,255,255,0.03)', borderRadius: radii.sm, padding: 10, border: `1px solid ${colors.borderSubtle}` }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: colors.textPrimary, marginBottom: 8 }}>
                  Detected active background apps:
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {noiseStatus.detected_apps.map((app) => (
                    <label key={app.key} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: colors.textSecondary, cursor: 'pointer' }}>
                      <input
                        type="checkbox"
                        checked={!!selectedAppsToQuiet[app.key]}
                        onChange={(e) => setSelectedAppsToQuiet((prev) => ({ ...prev, [app.key]: e.target.checked }))}
                        style={{ accentColor: '#818cf8' }}
                      />
                      <span>{app.name}</span>
                      <span style={{ fontSize: 10, fontFamily: fonts.mono, color: colors.textTertiary }}>
                        ({app.pids.length} process{app.pids.length > 1 ? 'es' : ''}, {(app.total_cpu_pct ?? 0).toFixed(1)}% CPU)
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            ) : (
              <div style={{ fontSize: 12, color: colors.textTertiary, marginBottom: 16 }}>
                No major app noise detected. System is ready for clean calibration.
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button
                onClick={() => setShowNoiseModal(false)}
                style={{
                  padding: '6px 14px',
                  borderRadius: radii.sm,
                  background: 'transparent',
                  border: `1px solid ${colors.border}`,
                  color: colors.textSecondary,
                  fontSize: 12,
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                onClick={() => executeStartCalibration(false)}
                style={{
                  padding: '6px 14px',
                  borderRadius: radii.sm,
                  background: 'rgba(255,255,255,0.08)',
                  border: 'none',
                  color: colors.textPrimary,
                  fontSize: 12,
                  cursor: 'pointer',
                }}
              >
                Start Without Closing
              </button>
              <button
                onClick={handleQuietApps}
                disabled={isQuieting}
                style={{
                  padding: '6px 16px',
                  borderRadius: radii.sm,
                  background: colors.accentBg,
                  border: 'none',
                  color: '#fff',
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: isQuieting ? 'wait' : 'pointer',
                }}
              >
                {isQuieting ? 'Closing Apps...' : '🧹 Quiet Apps & Start Sweep'}
              </button>
            </div>
          </div>
        </div>
      )}

      {error && (
        <div style={{ ...card, padding: 16, ...type.small, color: colors.amber }}>
          Calibration data unavailable: {error}
        </div>
      )}

      {/* C1 single-core reference cards */}
      {scopeFilter !== 'multi' && (
        <>
          <div style={{ ...sectionLabel, marginTop: 4 }}>Single-Core References (C1)</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
            {visibleClasses.filter((c) => c.c1?.runtime_s).map((c) => {
              const col = classColor(c.label);
              const tp = c.c1?.runtime_s ? 1000 / c.c1.runtime_s : undefined;
              return (
                <div key={c.label} style={{ ...card, padding: 16 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ ...type.h2, color: colors.textPrimary }}>
                      <span style={{ color: col, marginRight: 8 }}>●</span>
                      {classDisplayName(c)}
                    </div>
                    <span style={{ ...type.micro, color: colors.textQuaternary, fontFamily: fonts.mono }}>
                      {c.c1?.cpus?.length === 1 ? `cpu ${c.c1.cpus[0]}` : c.c1?.cpus ? `cpus ${c.c1.cpus.join(',')}` : 'single core'}
                    </span>
                  </div>
                  {c.c1?.runtime_s ? (
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginTop: 14 }}>
                      {[
                        { k: 'runtime', v: `${fmt(c.c1.runtime_s, 2)} s` },
                        { k: 'energy', v: `${fmt(c.c1.energy_j, 1)} J` },
                        { k: 'avg power', v: `${fmt((c.c1.energy_j ?? 0) / c.c1.runtime_s, 1)} W` },
                        { k: 'score', v: tp ? `${fmt(tp, 1)}` : '—' },
                        { k: 'score/W', v: tp ? fmt(tp / ((c.c1.energy_j ?? 0) / c.c1.runtime_s), 2) : '—' },
                        { k: 'status', v: 'Stock baseline' },
                      ].map((m) => (
                        <div key={m.k}>
                          <div style={{ ...type.micro, color: colors.textQuaternary, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{m.k}</div>
                          <div style={{ ...type.monoValue, color: colors.textPrimary, fontFamily: fonts.mono, marginTop: 2 }}>{m.v}</div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{ ...type.small, color: colors.textTertiary, marginTop: 12 }}>No single-core rows measured.</div>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* Performance vs Power curve card */}
      <div style={{ ...sectionLabel, marginTop: 8 }}>
        Efficiency Curve (Score vs Package Power)
        {scopeFilter === 'single' ? ' · Single-core' : scopeFilter === 'multi' ? ' · Multicore' : ' · All Points'}
      </div>

      <div style={{ ...card, padding: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, gap: 12, flexWrap: 'wrap' }}>
          <div style={{ ...type.small, color: colors.textSecondary, maxWidth: 620 }}>
            Higher score indicates faster completion. Package power measured in Watts.
            {data?.total_runs_aggregated ? ` (${data.total_runs_aggregated} live runs aggregated)` : ''}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button
              onClick={() => setShowPareto((v) => !v)}
              style={{
                ...type.smallMedium,
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '4px 10px',
                borderRadius: radii.sm,
                border: `1px solid ${showPareto ? '#22d3ee' : colors.border}`,
                background: showPareto ? '#22d3ee18' : 'transparent',
                color: showPareto ? '#22d3ee' : colors.textTertiary,
                cursor: 'pointer',
                font: 'inherit',
                fontSize: 12,
              }}
            >
              <span style={{ width: 12, height: 2, background: showPareto ? '#22d3ee' : colors.textTertiary, display: 'inline-block', borderBottom: '2px dashed #22d3ee' }} />
              Pareto Optimal Frontier
            </button>
          </div>
        </div>

        {/* Hover metadata badge — fixed height container ensures zero layout shifts or cursor jumping */}
        <div style={{ minHeight: 44, marginBottom: 12, display: 'flex', alignItems: 'center' }}>
          {hovered ? (
            <div
              style={{
                ...type.monoLabel,
                fontFamily: fonts.mono,
                color: colors.textSecondary,
                background: colors.surfaceElevated,
                border: `1px solid ${colors.border}`,
                borderRadius: radii.sm,
                padding: '6px 12px',
                display: 'flex',
                flexWrap: 'wrap',
                gap: 12,
                alignItems: 'center',
                width: '100%',
                boxSizing: 'border-box',
              }}
            >
              <span style={{ color: colors.textPrimary, fontWeight: 600 }}>{hovered.label}</span>
              {hovered.meta &&
                Object.entries(hovered.meta).map(([k, v]) => (
                  <span key={k}>
                    <span style={{ color: colors.textTertiary }}>{k}:</span> {v}
                  </span>
                ))}
            </div>
          ) : (
            <div
              style={{
                ...type.caption,
                color: colors.textQuaternary,
                paddingLeft: 4,
                fontStyle: 'italic',
              }}
            >
              Hover over any point to inspect configuration details, power draw, and performance score.
            </div>
          )}
        </div>

        {/* Graph rendering */}
        {(classFilter === 'combined' ? [null] : visibleClasses.map((c) => c.label)).map((single) => {
          const chartClasses = single ? visibleClasses.filter((c) => c.label === single) : visibleClasses;
          const pts: Point[] = chartClasses.flatMap((c) => {
            const list = filteredPointsByClass.get(c.label) ?? [];
            return list.map((p) => {
              const scoreVal = p.score ?? (p.throughput > 0 ? p.throughput : (p.runtime_s > 0 ? 1000 / p.runtime_s : 0));
              const subSeriesName = p.series || `${c.label} (${p.workers}w)`;
              return {
                x: p.watts,
                y: scoreVal,
                label: `${subSeriesName} · ${p.control}`,
                series: c.label,
                subSeries: subSeriesName,
                color: SERIES_PALETTE[subSeriesName] || classColor(c.label),
                meta: {
                  'Score': `${fmt(scoreVal, 1)} pts`,
                  'Avg Power': `${fmt(p.watts, 1)} W`,
                  'Avg Runtime': `${fmt(p.runtime_s, 2)} s`,
                  'Runs': p.n && p.n > 1 ? `avg of ${p.n} runs` : '1 run',
                  'Efficiency': `${fmt(p.perf_per_watt ?? (scoreVal / (p.watts || 1)), 2)} score/W`,
                  'Cores': `cpus ${p.cpus.join(',')}`,
                },
              };
            });
          });

          if (pts.length === 0) {
            return (
              <div key={single ?? 'combined'} style={{ ...type.small, color: colors.textTertiary, padding: '2rem 0', textAlign: 'center' }}>
                No measured points found for this selection.
              </div>
            );
          }

          return (
            <div
              key={single ?? 'combined'}
              style={{
                marginTop: single && chartClasses[0] !== visibleClasses[0] ? 20 : 0,
                paddingTop: single && chartClasses[0] !== visibleClasses[0] ? 16 : 0,
                borderTop: single && chartClasses[0] !== visibleClasses[0] ? `1px solid ${colors.borderSubtle}` : undefined,
              }}
            >
              {single && (
                <div style={{ ...type.smallMedium, color: classColor(single), marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: classColor(single) }} />
                  <span>{classDisplayName(chartClasses[0])}</span>
                </div>
              )}
              <ScatterChart
                points={pts}
                connectSeries
                showPareto={showPareto}
                series={seriesColors}
                seriesKey={(p) => p.subSeries || p.series || ''}
                xLabel="Package Power"
                yLabel="Performance Score"
                xUnit="Watts"
                yUnit="Higher is Faster"
                onHover={setHovered}
              />
            </div>
          );
        })}

        {/* Legend */}
        <div style={{ display: 'flex', gap: 16, marginTop: 14, flexWrap: 'wrap', borderTop: `1px solid ${colors.borderSubtle}`, paddingTop: 10 }}>
          {visibleClasses.flatMap((c) => {
            const list = filteredPointsByClass.get(c.label) ?? [];
            const subNames = Array.from(new Set(list.map((p) => p.series || `${c.label} (${p.workers}w)`)));
            return subNames.map((sName) => (
              <div key={sName} style={{ display: 'flex', alignItems: 'center', gap: 6, ...type.small, color: colors.textTertiary }}>
                <span style={{ width: 14, height: 3, borderRadius: 2, background: SERIES_PALETTE[sName] || classColor(c.label) }} />
                <span>{sName}</span>
              </div>
            ));
          })}
          {showPareto && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, ...type.small, color: '#22d3ee' }}>
              <span style={{ width: 14, height: 2, borderBottom: '2px dashed #22d3ee' }} />
              <span>Pareto Frontier (Optimal Efficiency)</span>
            </div>
          )}
        </div>
      </div>

      {/* Footer */}
      <div style={{ ...type.caption, color: colors.textQuaternary, padding: '0 4px 8px' }}>
        Hardware counter measurements with kernel output verification. Calibration benchmarks never skew workload selections.
        {data?.source ? ` Source: ${data.source}.` : ''}
      </div>
    </div>
  );
};
