import React, { useEffect, useMemo, useState } from 'react';
import { colors, fonts, fontFeatures, type, radii, card, sectionLabel } from '../design';

/* ------------------------------------------------------------------ */
/* data types                                                          */
/* ------------------------------------------------------------------ */

interface CalRow {
  class: string;
  control: string;
  workers: number;
  cpus: number[];
  runtime_s: number;
  package_energy_j: number;
  rep?: number;
}

interface CalPoint {
  control: string;
  workers: number;
  cpus: number[];
  scope: 'single' | 'multi';
  runtime_s: number;
  energy_j: number;
  watts: number;
  perfPerWatt: number;
  perf_per_watt?: number;
  throughput: number;
  scalingEfficiency?: number | null;
  scaling_efficiency?: number | null;
}

interface ClassSummary {
  label: string;
  hw_max_freq_khz?: number | null;
  c1?: { runtime_s: number; energy_j: number; cpus?: number[] } | null;
  points: CalPoint[];
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

/* ------------------------------------------------------------------ */
/* chart primitives (SVG)                                              */
/* ------------------------------------------------------------------ */

interface Point {
  x: number;
  y: number;
  label: string;
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
  height = 240,
  onHover,
  connectSeries,
}: {
  points: Point[];
  /** per-series color: map seriesKey -> css color */
  series: Record<string, string>;
  /** which series a point belongs to */
  seriesKey: (p: Point) => string;
  /** draw a connected line per series (efficiency curve) */
  connectSeries?: boolean;
  xLabel: string;
  yLabel: string;
  xUnit?: string;
  yUnit?: string;
  height?: number;
  onHover?: (p: Point | null) => void;
}) {
  const W = 560;
  const H = height;
  const M = { top: 14, right: 18, bottom: 40, left: 56 };
  const iw = W - M.left - M.right;
  const ih = H - M.top - M.bottom;

  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  if (xs.length === 0) return null;
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const yMin = 0;
  const yMax = Math.max(...ys) * 1.08;
  const xPad = (xMax - xMin) * 0.06 || 1;
  const yPad = (yMax - yMin) * 0.06 || 1;

  const sx = (v: number) => M.left + ((v - (xMin - xPad)) / (xMax - xMin + 2 * xPad)) * iw;
  const sy = (v: number) => H - M.bottom - ((v - (yMin - yPad * 0.1)) / (yMax + yPad - (yMin - yPad * 0.1))) * ih;

  const ticksY = 4;
  const tickVals = Array.from({ length: ticksY + 1 }, (_, i) => yMin + ((yMax - yMin) * i) / ticksY);
  const ticksX = 4;
  const xTickVals = Array.from({ length: ticksX + 1 }, (_, i) => xMin + ((xMax - xMin) * i) / ticksX);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto', display: 'block' }}>
      {tickVals.map((v, i) => (
        <g key={i}>
          <line x1={M.left} x2={W - M.right} y1={sy(v)} y2={sy(v)} stroke={colors.borderSubtle} strokeWidth={1} />
          <text x={M.left - 8} y={sy(v) + 3.5} textAnchor="end" fontSize={10} fill={colors.textQuaternary} fontFamily={fonts.mono}>
            {v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(v < 10 ? 1 : 0)}
          </text>
        </g>
      ))}
      {xTickVals.map((v, i) => (
        <text key={i} x={sx(v)} y={H - M.bottom + 14} textAnchor="middle" fontSize={10} fill={colors.textQuaternary} fontFamily={fonts.mono}>
          {v.toFixed(v < 10 ? 1 : 0)}
        </text>
      ))}

      <text x={M.left + iw / 2} y={H - 6} textAnchor="middle" fontSize={10} fill={colors.textTertiary}>
        {xLabel}{xUnit ? ` (${xUnit})` : ''}
      </text>
      <text
        x={12}
        y={M.top + ih / 2}
        textAnchor="middle"
        fontSize={10}
        fill={colors.textTertiary}
        transform={`rotate(-90 12 ${M.top + ih / 2})`}
      >
        {yLabel}{yUnit ? ` (${yUnit})` : ''}
      </text>

      {connectSeries &&
        // one sorted polyline per series so the curve reads as a curve
        Object.entries(
          points.reduce<Record<string, Point[]>>((acc, p) => {
            const k = seriesKey(p);
            (acc[k] ||= []).push(p);
            return acc;
          }, {}),
        ).map(([k, pts]) => {
          const sorted = [...pts].sort((a, b) => a.x - b.x);
          if (sorted.length < 2) return null; // a single point has no line — dot only
          const d = sorted
            .map((p, i) => `${i === 0 ? 'M' : 'L'} ${sx(p.x)} ${sy(p.y)}`)
            .join(' ');
          return (
            <path
              key={`line-${k}`}
              d={d}
              fill="none"
              stroke={series[k] ?? colors.textTertiary}
              strokeWidth={1.75}
              opacity={0.65}
              pointerEvents="none"
            />
          );
        })}

      {points.map((p, i) => {
        const col = series[seriesKey(p)] ?? colors.textTertiary;
        return (
          <g key={i} style={{ cursor: onHover ? 'crosshair' : 'default' }}>
            <circle
              cx={sx(p.x)}
              cy={sy(p.y)}
              r={9}
              fill="transparent"
              onMouseEnter={() => onHover?.(p)}
              onMouseLeave={() => onHover?.(null)}
            />
            <circle cx={sx(p.x)} cy={sy(p.y)} r={3.5} fill={col} stroke={colors.bg} strokeWidth={1.5} pointerEvents="none" />
          </g>
        );
      })}
    </svg>
  );
}

/* small pill toggle used by both pickers */
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
  const [hovered, setHovered] = useState<Point | null>(null);

  useEffect(() => {
    fetch('/api/calibration')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setData)
      .catch((e) => setError(String(e?.message ?? e)));
  }, []);

  const classes = data?.classes ?? [];
  const visibleClasses = classFilter === 'all' ? classes : classes.filter((c) => c.label === classFilter);
  const nPhys = data?.topology?.physical_cores;
  const nLog = data?.topology?.logical_cores;

  // points after both filters; "all-cores" scope = every multicore point we have
  // (a dedicated all-cores sweep row doesn't exist yet — flagged honestly below)
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
      {/* header + pickers */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <div style={{ ...type.display, color: colors.textPrimary }}>Calibration</div>
          <div style={{ ...type.small, color: colors.textTertiary, marginTop: 4 }}>
            Measured perf/power scaling — single-core references (C1) and the multicore perf/W
            curve (C2).
            {data?.captured_utc ? ` Captured ${data.captured_utc.slice(0, 16).replace('T', ' ')} UTC.` : ''}
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-end' }}>
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

      {/* all-cores honesty notice — only when genuinely unmeasured */}
      {scopeFilter === 'multi' && data && data.all_cores_measured === false && (
        <div style={{ ...card, padding: 12, ...type.small, color: colors.textTertiary, border: `1px solid ${colors.border}` }}>
          <span style={{ color: colors.amber, fontWeight: 600 }}>Not yet measured:</span> no all-cores
          calibration rows exist (nothing at {nPhys ?? '—'} physical / {nLog ?? '—'} logical workers).
          Showing the widest layouts that were calibrated.
        </div>
      )}

      {/* C1 single-core reference cards */}
      {scopeFilter !== 'multi' && (
        <>
          <div style={{ ...sectionLabel, marginTop: 4 }}>Single-core reference — C1 (stock, one core per class)</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
            {visibleClasses.map((c) => {
              const col = classColor(c.label);
              const tp = c.c1 ? 16384 / c.c1.runtime_s : undefined;
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
                        { k: 'throughput', v: tp ? `${fmt(tp, 0)} ch/s` : '—' },
                        { k: 'perf/W', v: tp ? fmt(tp / ((c.c1.energy_j ?? 0) / c.c1.runtime_s), 0) : '—' },
                        { k: 'work', v: '16384 ch' },
                      ].map((m) => (
                        <div key={m.k}>
                          <div style={{ ...type.micro, color: colors.textQuaternary, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{m.k}</div>
                          <div style={{ ...type.monoValue, color: colors.textPrimary, fontFamily: fonts.mono, marginTop: 2 }}>{m.v}</div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{ ...type.small, color: colors.textTertiary, marginTop: 12 }}>No C1 rows for this class.</div>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* Performance vs Power curve(s) */}
      <div style={{ ...sectionLabel, marginTop: 8 }}>
        Performance vs Power Curve (Performance on Y axis, Wattage on X axis)
        {scopeFilter === 'single' ? ' (single-core points)' : scopeFilter === 'multi' ? ' (multicore points)' : ' (all measured points)'}
      </div>
      <div style={{ ...card, padding: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, gap: 12, flexWrap: 'wrap' }}>
          <div style={{ ...type.small, color: colors.textSecondary, maxWidth: 640 }}>
            Performance (throughput on Y axis) vs package power (wattage in W on X axis). Higher is faster.
            Shows how much performance each core class delivers at different power levels.
          </div>
          {/* machine-fact honesty note: why the curve is 2 points on this laptop */}
          {data && classes.length > 0 && classes.every((c) => new Set(c.points.filter((p) => p.workers > 1).map((p) => p.control)).size <= 2) && (
            <div style={{ ...type.small, color: colors.textTertiary, maxWidth: 640, marginTop: 6, paddingTop: 6, borderTop: `1px solid ${colors.borderSubtle}` }}>
              <span style={{ color: colors.amber }}>Two control points per class</span> — measured machine
              fact (Gate B, see capability report): on this hardware frequency caps bind only with boost
              off, which clamps both classes to base clock (~2 GHz); intermediate caps all measure base.
              The effective control space is stock (boost on) vs base (boost off), so each curve is the
              measured segment between exactly those two operating points — not a missing sweep. A
              denser curve would need a machine whose caps bind across a frequency ladder (discrete P-state
              list) or working EPP tiers; the discovery code path handles both when present.
            </div>
          )}
          {hovered && (
            <div
              style={{
                ...type.monoLabel,
                fontFamily: fonts.mono,
                color: colors.textSecondary,
                background: colors.surfaceElevated,
                border: `1px solid ${colors.border}`,
                borderRadius: radii.sm,
                padding: '4px 8px',
              }}
            >
              {hovered.label}
              {hovered.meta ? Object.entries(hovered.meta).map(([k, v]) => ` · ${k}: ${v}`).join('') : ''}
            </div>
          )}
        </div>

        {/* single combined chart when "All classes", one chart per class otherwise */}
        {(classFilter === 'all' ? [null] : visibleClasses.map((c) => c.label)).map((single) => {
          const chartClasses = single ? visibleClasses.filter((c) => c.label === single) : visibleClasses;
          const pts: Point[] = chartClasses.flatMap((c) => {
            const list = filteredPointsByClass.get(c.label) ?? [];
            return list.map((p) => ({
              x: p.watts,
              y: p.throughput > 0 ? p.throughput : (p.runtime_s > 0 ? 16384 / p.runtime_s : 0),
              label: `${c.label} · ${p.control} · ${p.workers}w`,
              series: c.label,
              meta: {
                performance: `${fmt(p.throughput > 0 ? p.throughput : 16384 / p.runtime_s, 0)} chunks/s`,
                power: `${fmt(p.watts, 1)} W`,
                runtime: `${fmt(p.runtime_s, 2)}s`,
                energy: `${fmt(p.energy_j, 1)}J`,
                'perf/W': `${fmt((p as CalPoint & { perf_per_watt?: number }).perf_per_watt ?? p.perfPerWatt, 0)} ch/J`,
                'scaling eff': (p.scalingEfficiency ?? p.scaling_efficiency) ? `${(((p.scalingEfficiency ?? p.scaling_efficiency) as number) * 100).toFixed(0)}%` : '—',
              },
            }));
          });
          if (pts.length === 0) {
            return (
              <div key={single ?? 'all'} style={{ ...type.small, color: colors.textTertiary, padding: '1.5rem 0', textAlign: 'center' }}>
                No measured points for this selection.
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
                series={seriesColors}
                seriesKey={(p) => (p as Point & { series?: string }).series ?? ''}
                xLabel="Package Power"
                yLabel="Performance (Throughput)"
                xUnit="W"
                yUnit="chunks/s"
                onHover={setHovered}
              />
            </div>
          );
        })}

        {/* legend when combined */}
        {classFilter === 'all' && (
          <div style={{ display: 'flex', gap: 14, marginTop: 8, flexWrap: 'wrap' }}>
            {visibleClasses.map((c) => (
              <div key={c.label} style={{ display: 'flex', alignItems: 'center', gap: 6, ...type.small, color: colors.textTertiary }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: classColor(c.label) }} />
                {classDisplayName(c)}
              </div>
            ))}
          </div>
        )}

        {/* scaling efficiency readout */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12, marginTop: 16 }}>
          {visibleClasses.flatMap((c) =>
            (filteredPointsByClass.get(c.label) ?? [])
              .filter((p) => p.workers > 1)
              .map((p) => (
                <div key={`${c.label}-${p.control}-${p.workers}`} style={{ ...card, padding: 12, background: 'rgba(255,255,255,0.02)' }}>
                  <div style={{ ...type.micro, color: colors.textQuaternary, fontFamily: fonts.mono, textTransform: 'uppercase' }}>
                    {c.label} · {p.control} · {p.workers} workers
                  </div>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 6 }}>
                    <span style={{ ...type.h1, color: colors.textPrimary, fontSize: 18 }}>
                      {(p.scalingEfficiency ?? p.scaling_efficiency) ? `${(((p.scalingEfficiency ?? p.scaling_efficiency) as number) * 100).toFixed(0)}%` : '—'}
                    </span>
                    <span style={{ ...type.caption, color: colors.textTertiary }}>scaling efficiency vs C1</span>
                  </div>
                  <div style={{ ...type.monoLabel, color: colors.textTertiary, fontFamily: fonts.mono, marginTop: 4 }}>
                    {fmt(p.throughput, 0)} chunks/s · {fmt(p.watts, 1)} W · {fmt(p.energy_j, 1)} J
                  </div>
                </div>
              )),
          )}
        </div>
      </div>

      {/* footer honesty guard */}
      <div style={{ ...type.caption, color: colors.textQuaternary, padding: '0 4px 8px' }}>
        Package-domain energy from a verified hardware counter. Calibration data never mixes into workload
        Pareto selection; points here are measured medians with kernel checksum and boot-id recorded per
        row. {data?.source ? `Source: ${data.source}.` : ''}
      </div>
    </div>
  );
};
