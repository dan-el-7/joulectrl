import React, { useState, useMemo } from 'react';
import { ConfigSummary } from '../types';
import { colors } from '../design';

interface ParetoChartProps {
  configurations: Record<string, ConfigSummary>;
  selectedConfigId?: string;
  baselineConfigId?: string;
  deadlineS?: number | null;
  taskDurationS?: number | null;
  frontierConfigIds?: string[];
  onSelectConfig?: (configId: string) => void;
}

const LAYOUT_COLORS: Record<string, { bg: string; border: string; name: string; short: string }> = {
  A: { bg: colors.emerald, border: colors.emerald, name: 'Layout A: fast-class cores', short: 'Fast Cores' },
  B: { bg: colors.accent, border: colors.accentBg, name: 'Layout B: all physical cores', short: 'Physical Cores' },
  C: { bg: colors.amber, border: colors.amber, name: 'Layout C: all logical CPUs', short: 'All Logical CPUs' },
  D: { bg: colors.accentHover, border: colors.accent, name: 'Layout D: efficient-class cores', short: 'Dense Zen 5c' },
};

function formatDuration(sec: number | null | undefined): string {
  if (sec == null || !Number.isFinite(sec)) return '—';
  if (sec < 60) return `${sec.toFixed(1)}s`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}m ${s.toString().padStart(2, '0')}s`;
}

function formatEnergy(j: number | null | undefined): string {
  if (j == null || !Number.isFinite(j)) return '—';
  if (j >= 1e6) return `${(j / 1e6).toFixed(2)} MJ`;
  if (j >= 1000) return `${(j / 1000).toFixed(1)} kJ`;
  return `${Math.round(j)} J`;
}

export const ParetoChart: React.FC<ParetoChartProps> = ({
  configurations,
  selectedConfigId,
  baselineConfigId,
  deadlineS,
  taskDurationS,
  frontierConfigIds = [],
  onSelectConfig,
}) => {
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [viewFilter, setViewFilter] = useState<'frontier' | 'all'>('frontier');
  const [selectedLayout, setSelectedLayout] = useState<string>('ALL');

  const configsList = Object.values(configurations);
  if (configsList.length === 0) {
    return <div style={{ padding: '2rem', textAlign: 'center', color: colors.textTertiary }}>No configuration data available</div>;
  }

  // Find baseline benchmark runtime to derive relative slowdown factors
  const baseCfg = (baselineConfigId ? configurations[baselineConfigId] : undefined)
    || configsList.find((c) => c.is_baseline)
    || configsList[0];
  const baseRuntime = baseCfg?.median_runtime_s && baseCfg.median_runtime_s > 0
    ? baseCfg.median_runtime_s
    : Math.min(...configsList.map((c) => c.median_runtime_s));

  const isExtrapolated = Boolean(taskDurationS && taskDurationS > 0 && baseRuntime > 0);
  const taskDuration = taskDurationS && taskDurationS > 0 ? taskDurationS : baseRuntime;

  // Scale data points to task duration if extrapolation is requested
  const scaledMap: Record<string, {
    cfg: ConfigSummary;
    runtime: number;
    guardedRuntime: number;
    energy: number;
    isFeasible: boolean;
    isDominated: boolean;
  }> = {};

  configsList.forEach((cfg) => {
    const factor = baseRuntime > 0 ? cfg.median_runtime_s / baseRuntime : 1.0;
    const guardedFactor = baseRuntime > 0
      ? (cfg.guarded_runtime_s || cfg.median_runtime_s * 1.05) / baseRuntime
      : 1.0;
    const runtime = isExtrapolated ? taskDuration * factor : cfg.median_runtime_s;
    const guardedRuntime = isExtrapolated ? taskDuration * guardedFactor : cfg.guarded_runtime_s;
    const energy = isExtrapolated
      ? (cfg.median_energy_j != null ? cfg.median_energy_j * (taskDuration / baseRuntime) : 0)
      : (cfg.median_energy_j ?? 0);
    const isFeasible = deadlineS ? guardedRuntime <= deadlineS : true;

    scaledMap[cfg.config_id] = {
      cfg,
      runtime,
      guardedRuntime,
      energy,
      isFeasible,
      isDominated: false,
    };
  });

  const scaledList = Object.values(scaledMap);

  // Identify non-dominated points among all candidate configurations
  const nonDominatedMap = useMemo(() => {
    const set = new Set<string>();
    scaledList.forEach((ptA) => {
      let dominated = false;
      for (const ptB of scaledList) {
        if (ptA.cfg.config_id === ptB.cfg.config_id) continue;
        if (
          ptB.runtime <= ptA.runtime &&
          ptB.energy <= ptA.energy &&
          (ptB.runtime < ptA.runtime || ptB.energy < ptA.energy)
        ) {
          dominated = true;
          break;
        }
      }
      if (!dominated) {
        set.add(ptA.cfg.config_id);
      }
    });
    return set;
  }, [scaledList]);

  // Merge backend frontierConfigIds with local Pareto discovery
  const allFrontierIds = useMemo(() => {
    const set = new Set<string>([...frontierConfigIds, ...Array.from(nonDominatedMap)]);
    if (baselineConfigId) set.add(baselineConfigId);
    if (selectedConfigId) set.add(selectedConfigId);
    return set;
  }, [frontierConfigIds, nonDominatedMap, baselineConfigId, selectedConfigId]);

  // Mark dominated status
  scaledList.forEach((item) => {
    item.isDominated = !allFrontierIds.has(item.cfg.config_id);
  });

  // Filter items based on active layout and view filter
  const displayedItems = useMemo(() => {
    return scaledList.filter((item) => {
      const layout = item.cfg.configuration?.layout || 'A';
      if (selectedLayout !== 'ALL' && layout !== selectedLayout) {
        if (item.cfg.config_id !== selectedConfigId && item.cfg.config_id !== baselineConfigId) {
          return false;
        }
      }
      if (viewFilter === 'frontier') {
        return allFrontierIds.has(item.cfg.config_id);
      }
      return true;
    });
  }, [scaledList, selectedLayout, viewFilter, allFrontierIds, selectedConfigId, baselineConfigId]);

  // Build Pareto frontier curve points sorted by runtime
  // In frontier mode, this curve connects all non-dominated points, guaranteeing a smooth downward slope
  const frontierPoints = useMemo(() => {
    const source = selectedLayout === 'ALL'
      ? scaledList.filter((s) => allFrontierIds.has(s.cfg.config_id))
      : scaledList.filter((s) => {
          const l = s.cfg.configuration?.layout || 'A';
          return (l === selectedLayout || s.cfg.config_id === selectedConfigId || s.cfg.config_id === baselineConfigId) && allFrontierIds.has(s.cfg.config_id);
        });

    return source.sort((a, b) => a.runtime - b.runtime);
  }, [scaledList, allFrontierIds, selectedLayout, selectedConfigId, baselineConfigId]);

  // Calculate bounds with padding based on displayed points
  const activeForBounds = displayedItems.length > 0 ? displayedItems : scaledList;
  const runtimes = activeForBounds.map((s) => s.runtime);
  const energies = activeForBounds.map((s) => s.energy);
  const spanX = Math.max(...runtimes, deadlineS ?? 0) - Math.min(...runtimes, deadlineS ?? Infinity) || 1;
  const spanY = Math.max(...energies) - Math.min(...energies) || 1;
  const minX = Math.max(0, (Math.min(...runtimes, deadlineS ?? Infinity) || 0) - spanX * 0.15);
  const maxX = Math.max(...runtimes, deadlineS ?? 0) + spanX * 0.15;
  const minY = Math.max(0, Math.min(...energies) - spanY * 0.15);
  const maxY = Math.max(...energies) + spanY * 0.15;

  // Chart dimensions
  const width = 640;
  const height = 380;
  const padLeft = 74;
  const padRight = 30;
  const padTop = 30;
  const padBottom = 50;

  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;

  const scaleX = (val: number) => padLeft + ((val - minX) / (maxX - minX)) * chartW;
  const scaleY = (val: number) => padTop + chartH - ((val - minY) / (maxY - minY)) * chartH;

  const frontierPath =
    frontierPoints.length > 1
      ? frontierPoints
          .map((pt, i) => `${i === 0 ? 'M' : 'L'} ${scaleX(pt.runtime).toFixed(1)} ${scaleY(pt.energy).toFixed(1)}`)
          .join(' ')
      : '';

  const frontierAreaPath =
    frontierPoints.length > 1
      ? `${frontierPath} L ${scaleX(frontierPoints[frontierPoints.length - 1].runtime).toFixed(1)} ${padTop + chartH} L ${scaleX(frontierPoints[0].runtime).toFixed(1)} ${padTop + chartH} Z`
      : '';

  const hoveredItem = hoveredId ? scaledMap[hoveredId] : null;

  return (
    <div style={{ background: colors.surface, borderRadius: '0.75rem', padding: '1rem', border: `1px solid ${colors.border}`, boxShadow: colors.cardShadow }}>
      {/* Top Header: Title, Mode Toggle, and Layout Filters */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '0.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <h3 style={{ margin: 0, fontSize: '1rem', color: colors.textSecondary, fontWeight: 600 }}>
            Package Energy vs. Runtime (Pareto Frontier)
          </h3>
          {isExtrapolated && (
            <span
              style={{
                fontSize: '0.68rem',
                fontWeight: 600,
                padding: '0.15rem 0.5rem',
                borderRadius: '9999px',
                backgroundColor: colors.tint.accentSoft,
                color: colors.accentHover,
                border: `1px solid ${colors.tint.accentSoft}`,
              }}
            >
              Extrapolated for {formatDuration(taskDuration)} ({(taskDuration / baseRuntime).toFixed(1)}× scale)
            </span>
          )}
        </div>

        {/* View Mode Toggle: Clean Frontier Curve vs All Points */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', background: colors.surfaceElevated, padding: '2px', borderRadius: '0.375rem', border: `1px solid ${colors.border}` }}>
          <button
            type="button"
            onClick={() => setViewFilter('frontier')}
            style={{
              padding: '3px 8px',
              borderRadius: '0.25rem',
              fontSize: '0.72rem',
              fontWeight: viewFilter === 'frontier' ? 600 : 400,
              border: 'none',
              background: viewFilter === 'frontier' ? colors.accent : 'transparent',
              color: viewFilter === 'frontier' ? '#fff' : colors.textTertiary,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}
            title="Focus exclusively on the optimal Pareto tradeoff curve"
          >
            <span>✨</span>
            <span>Frontier Curve</span>
          </button>
          <button
            type="button"
            onClick={() => setViewFilter('all')}
            style={{
              padding: '3px 8px',
              borderRadius: '0.25rem',
              fontSize: '0.72rem',
              fontWeight: viewFilter === 'all' ? 600 : 400,
              border: 'none',
              background: viewFilter === 'all' ? colors.accent : 'transparent',
              color: viewFilter === 'all' ? '#fff' : colors.textTertiary,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}
            title="Display all swept benchmark candidates including dominated points"
          >
            <span>📊</span>
            <span>All Points ({scaledList.length})</span>
          </button>
        </div>
      </div>

      {/* Filterable Layout Chips */}
      <div style={{ display: 'flex', gap: '0.4rem', fontSize: '0.72rem', flexWrap: 'wrap', alignItems: 'center', marginBottom: '0.6rem', paddingBottom: '0.4rem', borderBottom: `1px solid ${colors.border}` }}>
        <span style={{ color: colors.textTertiary, fontSize: '0.7rem', fontWeight: 600, marginRight: '0.2rem' }}>Filter Layout:</span>
        <button
          type="button"
          onClick={() => setSelectedLayout('ALL')}
          style={{
            padding: '2px 7px',
            borderRadius: '0.25rem',
            border: `1px solid ${selectedLayout === 'ALL' ? colors.accentHover : colors.border}`,
            background: selectedLayout === 'ALL' ? colors.tint.accentSoft : 'transparent',
            color: selectedLayout === 'ALL' ? colors.accentHover : colors.textTertiary,
            fontSize: '0.7rem',
            cursor: 'pointer',
            fontWeight: selectedLayout === 'ALL' ? 600 : 400,
          }}
        >
          All Layouts
        </button>
        {Object.entries(LAYOUT_COLORS).map(([key, info]) => {
          const isSel = selectedLayout === key;
          return (
            <button
              key={key}
              type="button"
              onClick={() => setSelectedLayout(isSel ? 'ALL' : key)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.35rem',
                padding: '2px 7px',
                borderRadius: '0.25rem',
                border: `1px solid ${isSel ? info.bg : colors.border}`,
                background: isSel ? colors.tint.neutralStrong : 'transparent',
                color: isSel ? colors.textPrimary : colors.textTertiary,
                fontSize: '0.7rem',
                cursor: 'pointer',
                fontWeight: isSel ? 600 : 400,
              }}
            >
              <span style={{ width: 7, height: 7, borderRadius: '50%', backgroundColor: info.bg }} />
              <span>{info.short}</span>
            </button>
          );
        })}
      </div>

      <div style={{ position: 'relative' }}>
        <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: 'auto', display: 'block' }}>
          <defs>
            <linearGradient id="frontierAreaGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={colors.accentHover} stopOpacity="0.14" />
              <stop offset="100%" stopColor={colors.accentHover} stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
            const y = padTop + chartH * ratio;
            const energyVal = maxY - ratio * (maxY - minY);
            return (
              <g key={`y-grid-${ratio}`}>
                <line x1={padLeft} y1={y} x2={width - padRight} y2={y} stroke={colors.surfaceElevated} strokeDasharray="3 3" />
                <text x={padLeft - 8} y={y + 4} fill={colors.textTertiary} fontSize="10" textAnchor="end">
                  {formatEnergy(energyVal)}
                </text>
              </g>
            );
          })}

          {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
            const x = padLeft + chartW * ratio;
            const timeVal = minX + ratio * (maxX - minX);
            return (
              <g key={`x-grid-${ratio}`}>
                <line x1={x} y1={padTop} x2={x} y2={padTop + chartH} stroke={colors.surfaceElevated} strokeDasharray="3 3" />
                <text x={x} y={padTop + chartH + 18} fill={colors.textTertiary} fontSize="10" textAnchor="middle">
                  {formatDuration(timeVal)}
                </text>
              </g>
            );
          })}

          {/* Axes */}
          <line x1={padLeft} y1={padTop + chartH} x2={width - padRight} y2={padTop + chartH} stroke={colors.tint.neutralStrong} strokeWidth="1.5" />
          <line x1={padLeft} y1={padTop} x2={padLeft} y2={padTop + chartH} stroke={colors.tint.neutralStrong} strokeWidth="1.5" />

          <text x={padLeft + chartW / 2} y={height - 10} fill={colors.textTertiary} fontSize="11" textAnchor="middle">
            {isExtrapolated ? `Full Task Runtime (extrapolated from ${baseRuntime.toFixed(1)}s benchmark)` : 'Runtime (seconds) — Monotonic Clock'}
          </text>
          <text
            x={-height / 2}
            y={18}
            transform="rotate(-90)"
            fill={colors.textTertiary}
            fontSize="11"
            textAnchor="middle"
          >
            {isExtrapolated ? 'Extrapolated Package Energy' : 'Package Energy (Joules)'}
          </text>

          {/* Deadline Vertical Line */}
          {deadlineS && deadlineS >= minX && deadlineS <= maxX && (
            <g>
              <line
                x1={scaleX(deadlineS)}
                y1={padTop}
                x2={scaleX(deadlineS)}
                y2={padTop + chartH}
                stroke={colors.red}
                strokeWidth="1.5"
                strokeDasharray="4 4"
              />
              <text x={scaleX(deadlineS) + 4} y={padTop + 14} fill={colors.red} fontSize="10" fontWeight="bold">
                Budget {formatDuration(deadlineS)}
              </text>
            </g>
          )}

          {/* Shaded Area under Frontier Curve */}
          {frontierAreaPath && (
            <path
              d={frontierAreaPath}
              fill="url(#frontierAreaGrad)"
            />
          )}

          {/* Pareto Frontier Optimal Curve */}
          {frontierPath && (
            <path
              d={frontierPath}
              fill="none"
              stroke={colors.accentHover}
              strokeWidth="2.5"
              strokeDasharray="4 2"
              opacity="0.85"
            />
          )}

          {/* Data Points */}
          {displayedItems.map((item) => {
            const { cfg, runtime, guardedRuntime, energy, isFeasible, isDominated } = item;
            const cx = scaleX(runtime);
            const cy = scaleY(energy);
            const layoutKey = cfg.configuration?.layout || 'A';
            const color = LAYOUT_COLORS[layoutKey] || { bg: colors.textTertiary, border: colors.textTertiary };
            const isSelected = cfg.config_id === selectedConfigId;
            const isBaseline = cfg.config_id === baselineConfigId;
            const isHovered = cfg.config_id === hoveredId;
            const isFrontier = !isDominated || isBaseline || isSelected;

            // In all mode, gently fade dominated points to bring out the clean frontier
            const opacity = isHovered || isSelected || isBaseline
              ? 1.0
              : (isFrontier ? (isFeasible ? 0.95 : 0.6) : 0.25);
            const radius = isBaseline ? 7.5 : (isSelected ? 7.5 : (isFrontier ? 6 : 4));

            return (
              <g
                key={cfg.config_id}
                style={{ cursor: 'pointer', opacity }}
                onMouseEnter={() => setHoveredId(cfg.config_id)}
                onMouseLeave={() => setHoveredId(null)}
                onClick={() => onSelectConfig && onSelectConfig(cfg.config_id)}
              >
                {/* Guarded runtime bar */}
                <line
                  x1={cx}
                  y1={cy}
                  x2={scaleX(guardedRuntime)}
                  y2={cy}
                  stroke={isFeasible ? color.bg : colors.red}
                  strokeWidth="1.5"
                  opacity={isHovered ? 0.9 : 0.4}
                />
                <line
                  x1={scaleX(guardedRuntime)}
                  y1={cy - 4}
                  x2={scaleX(guardedRuntime)}
                  y2={cy + 4}
                  stroke={isFeasible ? color.bg : colors.red}
                  strokeWidth="1.5"
                  opacity={isHovered ? 0.9 : 0.4}
                />

                {/* Outer halo for selected or hovered */}
                {(isSelected || isHovered) && (
                  <circle
                    cx={cx}
                    cy={cy}
                    r={isSelected ? 11 : 9}
                    fill="none"
                    stroke={isSelected ? colors.emerald : (isFeasible ? colors.accentHover : colors.red)}
                    strokeWidth="2"
                    strokeDasharray={isSelected ? 'none' : '2 2'}
                  />
                )}

                {/* Point circle */}
                <circle
                  cx={cx}
                  cy={cy}
                  r={radius}
                  fill={isBaseline ? colors.red : color.bg}
                  stroke={!isFeasible ? colors.red : (isBaseline ? colors.red : color.border)}
                  strokeWidth="1.5"
                />

                {/* Marker text for baseline / selected */}
                {isBaseline && (
                  <text x={cx} y={cy - 10} fill={colors.red} fontSize="9" fontWeight="bold" textAnchor="middle">
                    Baseline
                  </text>
                )}
                {isSelected && !isBaseline && (
                  <text x={cx} y={cy - 14} fill={colors.emerald} fontSize="9" fontWeight="bold" textAnchor="middle">
                    Selected ★
                  </text>
                )}
              </g>
            );
          })}
        </svg>

        {/* Floating Tooltip */}
        {hoveredItem && (
          <div
            style={{
              position: 'absolute',
              top: '10px',
              right: '15px',
              background: colors.surfaceElevated,
              border: `1px solid ${hoveredItem.isFeasible ? colors.tint.neutralStrong : colors.tint.dangerBorder}`,
              borderRadius: '0.5rem',
              padding: '0.6rem 0.8rem',
              fontSize: '0.75rem',
              color: colors.textPrimary,
              boxShadow: `0 4px 6px -1px ${colors.tint.overlay}`,
              pointerEvents: 'none',
              maxWidth: '280px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem' }}>
              <span style={{ fontWeight: 600, color: colors.accentHover }}>{hoveredItem.cfg.config_id}</span>
              <span
                style={{
                  fontSize: '0.68rem',
                  fontWeight: 600,
                  color: hoveredItem.isFeasible ? colors.emerald : colors.red,
                }}
              >
                {hoveredItem.isFeasible ? 'Within Budget' : 'Exceeds Budget'}
              </span>
            </div>
            <div>Layout: {LAYOUT_COLORS[hoveredItem.cfg.configuration?.layout]?.name ?? hoveredItem.cfg.configuration?.layout}</div>
            <div>Workers: {hoveredItem.cfg.configuration?.worker_count} | Boost: {hoveredItem.cfg.configuration?.boost ? 'On' : 'Off'}</div>
            <div>Cap: {hoveredItem.cfg.configuration?.freq_cap_khz ? `${hoveredItem.cfg.configuration.freq_cap_khz / 1e6} GHz` : 'Stock'}</div>
            {hoveredItem.isDominated && (
              <div style={{ color: colors.amber, fontSize: '0.68rem', marginTop: '0.2rem' }}>Dominated configuration (slower and higher energy than frontier)
              </div>
            )}
            <div style={{ marginTop: '0.3rem', borderTop: `1px solid ${colors.tint.neutralStrong}`, paddingTop: '0.3rem' }}>
              <div>
                <strong>Runtime:</strong> {formatDuration(hoveredItem.runtime)} (guarded: {formatDuration(hoveredItem.guardedRuntime)})
              </div>
              <div>
                <strong>Energy:</strong> {formatEnergy(hoveredItem.energy)} (avg {hoveredItem.cfg.median_power_w} W)
              </div>
              {isExtrapolated && (
                <div style={{ fontSize: '0.68rem', color: colors.textTertiary, marginTop: '0.2rem' }}>
                  Measured benchmark: {hoveredItem.cfg.median_runtime_s}s · {hoveredItem.cfg.median_energy_j} J
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

