import React, { useEffect, useMemo, useState } from 'react';
import { fetchCalibration } from '../api';
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

type ClassFilter = 'all' | string;
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
      : colors.series.accent2;

/** Data-driven class display name: "fast · ≤5.09 GHz" — never hardcoded core names. */
const classDisplayName = (c: ClassSummary) => {
  if (c.label === 'all') return 'all cores (mixed classes)';
  return c.hw_max_freq_khz ? `${c.label} · ≤${(c.hw_max_freq_khz / 1e6).toFixed(2)} GHz` : c.label;
};

const SERIES_PALETTE: Record<string, string> = {
  'Zen 5 (4 cores)': '#a78bfa',
  'Zen 5 (8 threads)': '#c084fc',
  'Zen 5c (4 cores)': '#34d399',
  'All Cores (8 cores)': '#38bdf8',
  'All Cores (16 threads)': '#60a5fa',
  'fast': colors.series.fast,
  'efficient': colors.series.efficient,
  'all': colors.series.accent2,
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
    return acc;
  }, [points, seriesKey]);

  // Compute Pareto Optimal Frontier across all visible points
  const paretoPoints = useMemo(() => {
    const sorted = [...points].sort((a, b) => a.x - b.x);
    const frontier: Point[] = [];
    let maxY = -Infinity;
    for (const p of sorted) {
      if (p.y > maxY) {
        frontier.push(p);
        maxY = p.y;
      }
    }
    return frontier;
  }, [points]);

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

      {/* Pareto frontier curve (if enabled and >= 2 points) */}
      {showPareto && paretoPoints.length >= 2 && (
        <g>
          <path
            d={paretoPoints.map((p, i) => `${i === 0 ? 'M' : 'L'} ${sx(p.x)} ${sy(p.y)}`).join(' ')}
            fill="none"
            stroke="#22d3ee"
            strokeWidth={2}
            strokeDasharray="5 3"
            opacity={0.8}
            pointerEvents="none"
          />
        </g>
      )}

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

  useEffect(() => {
    fetchCalibration(selectedExpId || undefined)
      .then(setData)
      .catch((e) => setError(String(e?.message ?? e)));
  }, [selectedExpId]);

  const classes = data?.classes ?? [];
  const visibleClasses = classFilter === 'all' ? classes : classes.filter((c) => c.label === classFilter);

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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 1160, margin: '0 auto', fontFamily: fonts.sans, fontFeatureSettings: fontFeatures }}>
      {/* header + controls */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <div style={{ ...type.display, color: colors.textPrimary }}>Calibration & Silicon Benchmark</div>
          <div style={{ ...type.small, color: colors.textTertiary, marginTop: 4 }}>
            Measured performance vs power curves. Faster task completion gives higher score.
            Identical runs are averaged for measurement accuracy.
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
            {visibleClasses.map((c) => {
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
        Performance vs Power Curve (Higher is Faster, Wattage on X Axis)
        {scopeFilter === 'single' ? ' · Single-core' : scopeFilter === 'multi' ? ' · Multicore' : ' · All Points'}
      </div>

      <div style={{ ...card, padding: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, gap: 12, flexWrap: 'wrap' }}>
          <div style={{ ...type.small, color: colors.textSecondary, maxWidth: 620 }}>
            Faster task completion gives a higher score. Power is package wattage in Watts.
            Points sharing identical hardware frequency and cores are averaged.
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

        {/* Hover metadata badge */}
        {hovered && (
          <div
            style={{
              ...type.monoLabel,
              fontFamily: fonts.mono,
              color: colors.textSecondary,
              background: colors.surfaceElevated,
              border: `1px solid ${colors.border}`,
              borderRadius: radii.sm,
              padding: '6px 12px',
              marginBottom: 12,
              display: 'flex',
              flexWrap: 'wrap',
              gap: 12,
              alignItems: 'center',
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
        )}

        {/* Graph rendering */}
        {(classFilter === 'all' ? [null] : visibleClasses.map((c) => c.label)).map((single) => {
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
              <div key={single ?? 'all'} style={{ ...type.small, color: colors.textTertiary, padding: '2rem 0', textAlign: 'center' }}>
                No measured points found for this selection.
              </div>
            );
          }

          return (
            <div key={single ?? 'all'} style={{ marginTop: single ? 12 : 0 }}>
              {single && (
                <div style={{ ...type.smallMedium, color: classColor(single), marginBottom: 6 }}>
                  {classDisplayName(chartClasses[0])}
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
