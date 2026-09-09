import React, { useEffect, useMemo, useState } from 'react';
import { colors, fonts, fontFeatures, type, radii, card, sectionLabel, primaryButton } from '../design';

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

interface ClassSummary {
  label: string;          // "fast" | "efficient"
  c1?: { runtime_s: number; energy_j: number; cpus?: number[] };        // single-core stock reference
  points: {               // multicore (C2) points
    control: string;
    workers: number;
    runtime_s: number;    // median
    energy_j: number;     // median
    watts: number;
    perfPerWatt: number;  // throughput per watt (relative units ok)
    throughput: number;
    scalingEfficiency?: number; // vs C1 single-core
  }[];
}

interface CalibrationData {
  source: string;
  captured_utc?: string;
  kernel?: string;
  classes: ClassSummary[];
}

/* ------------------------------------------------------------------ */
/* helpers                                                             */
/* ------------------------------------------------------------------ */

const median = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

const fmt = (v: number | undefined, digits = 1) =>
  v == null || Number.isNaN(v) ? '—' : v.toFixed(digits);

const classColor = (label: string) =>
  label === 'fast' ? colors.series.fast : colors.series.efficient;

/* ------------------------------------------------------------------ */
/* load + aggregate                                                    */
/* ------------------------------------------------------------------ */

async function loadCalibration(): Promise<CalibrationData> {
  const res = await fetch('/api/calibration');
  if (!res.ok) throw new Error(`calibration fetch failed: ${res.status}`);
  return res.json();
}

function aggregate(rows: CalRow[], c1Rows: CalRow[]): ClassSummary[] {
  const byClass = new Map<string, CalRow[]>();
  for (const r of rows) {
    if (!byClass.has(r.class)) byClass.set(r.class, []);
    byClass.get(r.class)!.push(r);
  }
  const classes: ClassSummary[] = [];
  for (const [label, clsRows] of byClass) {
    // group multicore rows by (control, workers)
    const groups = new Map<string, CalRow[]>();
    for (const r of clsRows) {
      const key = `${r.control}:${r.workers}`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(r);
    }
    // C1 single-core stock reference (workers=1, stock) — one per class
    const c1ForClass = c1Rows.filter((r) => r.class === label);
    const c1 = c1ForClass.length
      ? {
          runtime_s: median(c1ForClass.map((r) => r.runtime_s)),
          energy_j: median(c1ForClass.map((r) => r.package_energy_j)),
        }
      : undefined;

    const points = [...groups.entries()]
      .map(([key, rs]) => {
        const control = rs[0].control;
        const workers = rs[0].workers;
        const runtime_s = median(rs.map((r) => r.runtime_s));
        const energy_j = median(rs.map((r) => r.package_energy_j));
        const watts = energy_j / runtime_s;
        const chunks = (rs[0] as any).chunks ?? 32768;
        const throughput = chunks / runtime_s;
        const perfPerWatt = throughput / watts;
        const scalingEfficiency =
          c1 && workers > 1
            ? throughput / (workers * (chunks / c1.runtime_s) / 1)
            : undefined;
        return { control, workers, runtime_s, energy_j, watts, perfPerWatt, throughput, scalingEfficiency };
      })
      .sort((a, b) => a.perfPerWatt - b.perfPerWatt);

    classes.push({ label, c1, points });
  }
  // fast class first
  classes.sort((a, b) => (a.label === 'fast' ? -1 : b.label === 'fast' ? 1 : 0));
  return classes;
}

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
  color,
  xLabel,
  yLabel,
  xUnit,
  yUnit,
  height = 240,
  yStartsAtZero = true,
  log = false,
  onHover,
}: {
  points: Point[];
  color: string;
  xLabel: string;
  yLabel: string;
  xUnit?: string;
  yUnit?: string;
  height?: number;
  yStartsAtZero?: boolean;
  log?: boolean;
  onHover?: (p: Point | null) => void;
}) {
  const W = 560;
  const H = height;
  const M = { top: 14, right: 18, bottom: 40, left: 56 };
  const iw = W - M.left - M.right;
  const ih = H - M.top - M.bottom;

  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const xMin = Math.min(...xs, Infinity);
  const xMax = Math.max(...xs, -Infinity);
  const yMin = yStartsAtZero ? 0 : Math.min(...ys, Infinity);
  const yMax = Math.max(...ys, -Infinity) * 1.08;
  const xPad = (xMax - xMin) * 0.06 || 1;
  const yPad = (yMax - yMin) * 0.06 || 1;

  const sx = (v: number) =>
    M.left + ((v - (xMin - xPad)) / (xMax - xMin + 2 * xPad)) * iw;
  const sy = (v: number) =>
    H - M.bottom - ((v - (yMin - yPad * 0.1)) / (yMax + yPad - (yMin - yPad * 0.1))) * ih;
  // note: log option reserved for future dense sweeps

  const ticksY = 4;
  const tickVals = Array.from({ length: ticksY + 1 }, (_, i) => yMin + ((yMax - yMin) * i) / ticksY);
  const ticksX = 4;
  const xTickVals = Array.from({ length: ticksX + 1 }, (_, i) => xMin + ((xMax - xMin) * i) / ticksX);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto', display: 'block' }}>
      {/* grid — whisper thin */}
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

      {/* axes labels */}
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

      {/* points */}
      {points.map((p, i) => (
        <g key={i} style={{ cursor: onHover ? 'crosshair' : 'default' }}>
          <circle
            cx={sx(p.x)}
            cy={sy(p.y)}
            r={9}
            fill="transparent"
            onMouseEnter={() => onHover?.(p)}
            onMouseLeave={() => onHover?.(null)}
          />
          <circle
            cx={sx(p.x)}
            cy={sy(p.y)}
            r={3.5}
            fill={color}
            stroke={colors.bg}
            strokeWidth={1.5}
            pointerEvents="none"
          />
        </g>
      ))}
    </svg>
  );
}

function Sparkline({ values, color, height = 44 }: { values: number[]; color: string; height?: number }) {
  if (values.length < 2) return <div style={{ height }} />;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 1e-6);
  const pts = values
    .map((v, i) => `${(i / (values.length - 1)) * 100},${height - 3 - ((v - min) / span) * (height - 6)}`)
    .join(' ');
  return (
    <svg viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" style={{ width: '100%', height }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.2} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/* main view                                                           */
/* ------------------------------------------------------------------ */

export const CalibrationView: React.FC = () => {
  const [data, setData] = useState<CalibrationData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showClass, setShowClass] = useState<Record<string, boolean>>({ fast: true, efficient: true });
  const [hovered, setHovered] = useState<{ chart: string; p: Point } | null>(null);

  useEffect(() => {
    loadCalibration().then(setData).catch((e) => setError(String(e?.message ?? e)));
  }, []);

  const classes = data?.classes ?? [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 1160, margin: '0 auto', fontFamily: fonts.sans, fontFeatureSettings: fontFeatures }}>
      {/* header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <div style={{ ...type.display, color: colors.textPrimary }}>Calibration</div>
          <div style={{ ...type.small, color: colors.textTertiary, marginTop: 4 }}>
            Measured perf/power scaling per core class — single-core references (C1) and the multicore
            efficiency curve (C2). Control points: {data?.kernel ? 'verified readback' : '—'}
            {data?.captured_utc ? ` · captured ${data.captured_utc.slice(0, 16).replace('T', ' ')} UTC` : ''}
          </div>
        </div>

        {/* class toggles */}
        <div style={{ display: 'flex', gap: 6 }}>
          {classes.map((c) => {
            const on = showClass[c.label] !== false;
            const col = classColor(c.label);
            return (
              <button
                key={c.label}
                onClick={() => setShowClass((p) => ({ ...p, [c.label]: !on }))}
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
                  cursor: 'pointer',
                  font: 'inherit',
                  fontSize: 12,
                }}
              >
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: on ? col : colors.textQuaternary }} />
                {c.label === 'fast' ? 'Zen 5 · fast' : 'Zen 5c · efficient'}
              </button>
            );
          })}
        </div>
      </div>

      {error && (
        <div style={{ ...card, padding: 16, ...type.small, color: colors.amber }}>
          Calibration data unavailable: {error}
        </div>
      )}

      {/* C1 single-core reference cards */}
      <div style={{ ...sectionLabel, marginTop: 4 }}>Single-core reference — C1 (stock, one core per class)</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
        {classes
          .filter((c) => showClass[c.label] !== false)
          .map((c) => {
            const col = classColor(c.label);
            const tp = c.c1 ? 16384 / c.c1.runtime_s : undefined; // chunks/s from C1 kernel
            return (
              <div key={c.label} style={{ ...card, padding: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ ...type.h2, color: colors.textPrimary }}>
                    <span style={{ color: col, marginRight: 8 }}>●</span>
                    {c.label}
                  </div>
                  <span style={{ ...type.micro, color: colors.textQuaternary, fontFamily: fonts.mono }}>
                    {c.c1?.cpus?.length === 1 ? `cpu ${c.c1.cpus[0]}` : c.c1?.cpus ? `cpus ${c.c1.cpus.join(',')}` : 'single core'}
                  </span>
                </div>
                {c.c1 ? (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginTop: 14 }}>
                    {[
                      { k: 'runtime', v: `${fmt(c.c1.runtime_s, 2)} s` },
                      { k: 'energy', v: `${fmt(c.c1.energy_j, 1)} J` },
                      { k: 'avg power', v: `${fmt(c.c1.energy_j / c.c1.runtime_s, 1)} W` },
                      { k: 'throughput', v: tp ? `${fmt(tp, 0)} ch/s` : '—' },
                      { k: 'perf/W', v: tp ? fmt(tp / (c.c1.energy_j / c.c1.runtime_s), 0) : '—' },
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

      {/* C2 multicore perf/W curve */}
      <div style={{ ...sectionLabel, marginTop: 8 }}>Multicore efficiency — C2 perf/W by control point</div>
      <div style={{ ...card, padding: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <div style={{ ...type.small, color: colors.textSecondary }}>
            Throughput per package-watt at each measured control point (4 workers, one SMT sibling each).
            Higher is better. Same-energy-lower-throughput points are dominated.
          </div>
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
              {hovered.p.label}
              {hovered.p.meta
                ? Object.entries(hovered.p.meta)
                    .map(([k, v]) => ` · ${k}: ${v}`)
                    .join('')
                : ''}
            </div>
          )}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
          {classes
            .filter((c) => showClass[c.label] !== false)
            .map((c) => {
              const col = classColor(c.label);
              const pts: Point[] = c.points.map((p) => ({
                x: p.watts,
                y: p.perfPerWatt,
                label: `${c.label} · ${p.control} · ${p.workers}w`,
                meta: {
                  runtime: `${fmt(p.runtime_s, 2)}s`,
                  energy: `${fmt(p.energy_j, 1)}J`,
                  'scaling eff': p.scalingEfficiency ? `${(p.scalingEfficiency * 100).toFixed(0)}%` : '—',
                },
              }));
              return (
                <div key={c.label}>
                  <div style={{ ...type.smallMedium, color: col, marginBottom: 6 }}>
                    {c.label === 'fast' ? 'Zen 5 (fast class)' : 'Zen 5c (efficient class)'}
                  </div>
                  <ScatterChart
                    points={pts}
                    color={col}
                    xLabel="avg package power"
                    yLabel="perf / W"
                    xUnit="W"
                    onHover={(p) => setHovered(p ? { chart: c.label, p } : null)}
                  />
                </div>
              );
            })}
        </div>

        {/* scaling efficiency readout */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12, marginTop: 16 }}>
          {classes
            .filter((c) => showClass[c.label] !== false)
            .flatMap((c) =>
              c.points
                .filter((p) => p.workers > 1)
                .map((p) => (
                  <div key={`${c.label}-${p.control}-${p.workers}`} style={{ ...card, padding: 12, background: 'rgba(255,255,255,0.02)' }}>
                    <div style={{ ...type.micro, color: colors.textQuaternary, fontFamily: fonts.mono, textTransform: 'uppercase' }}>
                      {c.label} · {p.control} · {p.workers} workers
                    </div>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 6 }}>
                      <span style={{ ...type.h1, color: colors.textPrimary, fontSize: 18 }}>
                        {p.scalingEfficiency ? `${(p.scalingEfficiency * 100).toFixed(0)}%` : '—'}
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
        Pareto selection; points here are measured medians (n = 3 reps) with kernel checksum and boot-id
        recorded per row. {data?.source ? `Source: ${data.source}.` : ''}
      </div>
    </div>
  );
};
