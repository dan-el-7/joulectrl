import React, { useState } from 'react';
import { ConfigSummary } from '../types';
import { colors } from '../design';

interface ParetoChartProps {
  configurations: Record<string, ConfigSummary>;
  selectedConfigId?: string;
  baselineConfigId?: string;
  deadlineS?: number | null;
  frontierConfigIds?: string[];
  onSelectConfig?: (configId: string) => void;
}

const LAYOUT_COLORS: Record<string, { bg: string; border: string; name: string }> = {
  A: { bg: colors.emerald, border: colors.emerald, name: 'Layout A: fast-class cores' },
  B: { bg: colors.accent, border: colors.accentBg, name: 'Layout B: all physical cores' },
  C: { bg: colors.amber, border: colors.amber, name: 'Layout C: all logical CPUs' },
  D: { bg: colors.accentHover, border: colors.accent, name: 'Layout D: efficient-class cores' },
};

export const ParetoChart: React.FC<ParetoChartProps> = ({
  configurations,
  selectedConfigId,
  baselineConfigId,
  deadlineS,
  frontierConfigIds = [],
  onSelectConfig,
}) => {
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const configsList = Object.values(configurations);
  if (configsList.length === 0) {
    return <div style={{ padding: '2rem', textAlign: 'center', color: colors.textTertiary }}>No configuration data available</div>;
  }

  // Calculate bounds with padding
  const runtimes = configsList.map((c) => c.median_runtime_s);
  const energies = configsList.map((c) => c.median_energy_j);
  const minX = Math.min(...runtimes, deadlineS ?? runtimes[0]) * 0.85;
  const maxX = Math.max(...runtimes, deadlineS ?? runtimes[0]) * 1.15;
  const minY = Math.min(...energies) * 0.85;
  const maxY = Math.max(...energies) * 1.15;

  // Chart dimensions
  const width = 640;
  const height = 380;
  const padLeft = 70;
  const padRight = 30;
  const padTop = 30;
  const padBottom = 50;

  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;

  const scaleX = (val: number) => padLeft + ((val - minX) / (maxX - minX)) * chartW;
  const scaleY = (val: number) => padTop + chartH - ((val - minY) / (maxY - minY)) * chartH;

  // Build Pareto frontier curve points sorted by runtime
  const frontierPoints = frontierConfigIds
    .map((id) => configurations[id])
    .filter(Boolean)
    .sort((a, b) => a.median_runtime_s - b.median_runtime_s);

  const frontierPath =
    frontierPoints.length > 1
      ? frontierPoints
          .map((pt, i) => `${i === 0 ? 'M' : 'L'} ${scaleX(pt.median_runtime_s)} ${scaleY(pt.median_energy_j)}`)
          .join(' ')
      : '';

  const hoveredConfig = hoveredId ? configurations[hoveredId] : null;

  return (
    <div style={{ background: colors.surface, borderRadius: '0.75rem', padding: '1rem', border: colors.border }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
        <h3 style={{ margin: 0, fontSize: '1rem', color: colors.textSecondary, fontWeight: 600 }}>
          Package Energy vs. Runtime (Pareto Frontier)
        </h3>
        <div style={{ display: 'flex', gap: '0.75rem', fontSize: '0.75rem', flexWrap: 'wrap' }}>
          {Object.entries(LAYOUT_COLORS).map(([key, info]) => (
            <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', color: colors.textTertiary }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: info.bg }} />
              <span>{info.name}</span>
            </div>
          ))}
        </div>
      </div>

      <div style={{ position: 'relative' }}>
        <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: 'auto', display: 'block' }}>
          {/* Grid lines */}
          {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
            const y = padTop + chartH * ratio;
            const energyVal = Math.round(maxY - ratio * (maxY - minY));
            return (
              <g key={`y-grid-${ratio}`}>
                <line x1={padLeft} y1={y} x2={width - padRight} y2={y} stroke={colors.surfaceElevated} strokeDasharray="3 3" />
                <text x={padLeft - 8} y={y + 4} fill={colors.textTertiary} fontSize="10" textAnchor="end">
                  {energyVal} J
                </text>
              </g>
            );
          })}

          {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
            const x = padLeft + chartW * ratio;
            const timeVal = (minX + ratio * (maxX - minX)).toFixed(1);
            return (
              <g key={`x-grid-${ratio}`}>
                <line x1={x} y1={padTop} x2={x} y2={padTop + chartH} stroke={colors.surfaceElevated} strokeDasharray="3 3" />
                <text x={x} y={padTop + chartH + 18} fill={colors.textTertiary} fontSize="10" textAnchor="middle">
                  {timeVal}s
                </text>
              </g>
            );
          })}

          {/* Axes */}
          <line x1={padLeft} y1={padTop + chartH} x2={width - padRight} y2={padTop + chartH} stroke="rgba(255,255,255,0.08)" strokeWidth="1.5" />
          <line x1={padLeft} y1={padTop} x2={padLeft} y2={padTop + chartH} stroke="rgba(255,255,255,0.08)" strokeWidth="1.5" />

          <text x={padLeft + chartW / 2} y={height - 10} fill={colors.textTertiary} fontSize="11" textAnchor="middle">
            Runtime (seconds) — Monotonic Clock
          </text>
          <text
            x={-height / 2}
            y={20}
            transform="rotate(-90)"
            fill={colors.textTertiary}
            fontSize="11"
            textAnchor="middle"
          >
            CPU-Package Energy (Joules)
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
                Budget {deadlineS}s
              </text>
            </g>
          )}

          {/* Pareto Frontier Curve */}
          {frontierPath && (
            <path
              d={frontierPath}
              fill="none"
              stroke={colors.accentHover}
              strokeWidth="2"
              strokeDasharray="4 2"
              opacity="0.75"
            />
          )}

          {/* Data Points */}
          {configsList.map((cfg) => {
            const cx = scaleX(cfg.median_runtime_s);
            const cy = scaleY(cfg.median_energy_j);
            const layoutKey = cfg.configuration.layout || 'D';
            const color = LAYOUT_COLORS[layoutKey] || { bg: colors.textTertiary, border: colors.textTertiary };
            const isSelected = cfg.config_id === selectedConfigId;
            const isBaseline = cfg.config_id === baselineConfigId;
            const isHovered = cfg.config_id === hoveredId;

            return (
              <g
                key={cfg.config_id}
                style={{ cursor: 'pointer' }}
                onMouseEnter={() => setHoveredId(cfg.config_id)}
                onMouseLeave={() => setHoveredId(null)}
                onClick={() => onSelectConfig && onSelectConfig(cfg.config_id)}
              >
                {/* Guarded runtime bar */}
                <line
                  x1={cx}
                  y1={cy}
                  x2={scaleX(cfg.guarded_runtime_s)}
                  y2={cy}
                  stroke={color.bg}
                  strokeWidth="1.5"
                  opacity={isHovered ? 0.9 : 0.4}
                />
                <line
                  x1={scaleX(cfg.guarded_runtime_s)}
                  y1={cy - 4}
                  x2={scaleX(cfg.guarded_runtime_s)}
                  y2={cy + 4}
                  stroke={color.bg}
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
                    stroke={isSelected ? colors.emerald : colors.accentHover}
                    strokeWidth="2"
                    strokeDasharray={isSelected ? 'none' : '2 2'}
                  />
                )}

                {/* Point circle */}
                <circle
                  cx={cx}
                  cy={cy}
                  r={isBaseline ? 7 : 6}
                  fill={isBaseline ? colors.red : color.bg}
                  stroke={isBaseline ? colors.red : color.border}
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
        {hoveredConfig && (
          <div
            style={{
              position: 'absolute',
              top: '10px',
              right: '15px',
              background: colors.surfaceElevated,
              border: '1px solid rgba(255,255,255,0.08)',
              borderRadius: '0.5rem',
              padding: '0.6rem 0.8rem',
              fontSize: '0.75rem',
              color: colors.textPrimary,
              boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.4)',
              pointerEvents: 'none',
              maxWidth: '260px',
            }}
          >
            <div style={{ fontWeight: 600, color: colors.accentHover, marginBottom: '0.25rem' }}>
              {hoveredConfig.config_id}
            </div>
            <div>Layout: {LAYOUT_COLORS[hoveredConfig.configuration.layout]?.name ?? hoveredConfig.configuration.layout}</div>
            <div>Workers: {hoveredConfig.configuration.worker_count} | Boost: {hoveredConfig.configuration.boost ? 'On' : 'Off'}</div>
            <div>Cap: {hoveredConfig.configuration.freq_cap_khz ? `${hoveredConfig.configuration.freq_cap_khz / 1e6} GHz` : 'Stock'}</div>
            <div style={{ marginTop: '0.3rem', borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '0.3rem' }}>
              <div><strong>Runtime:</strong> {hoveredConfig.median_runtime_s}s (guarded: {hoveredConfig.guarded_runtime_s}s)</div>
              <div><strong>Energy:</strong> {hoveredConfig.median_energy_j} J (avg {hoveredConfig.median_power_w} W)</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
