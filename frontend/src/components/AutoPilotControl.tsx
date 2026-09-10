import React, { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import {
  fetchAutoPilotStatus,
  armAutoPilot,
  disarmAutoPilot,
  fetchAutoPilotCurveOptions,
  AutoPilotStatus,
  AutoPilotCurveOption,
  AutoPilotCurvePoint,
} from '../api';
import { fonts, fontFeatures, radii, type } from '../design';
import { useTheme } from '../ThemeContext';

export interface AutoPilotControlProps {
  compact?: boolean;
  onStatusChange?: (status: AutoPilotStatus) => void;
}

function matchFrontierPoint(
  curve: AutoPilotCurveOption,
  targetSavingsPct: number
): { matchedPoint: AutoPilotCurvePoint; isAchievable: boolean } | null {
  if (!curve || !curve.frontier_points || curve.frontier_points.length === 0) return null;
  const eligible = curve.frontier_points.filter((p) => p.energy_reduction_pct >= targetSavingsPct);
  if (eligible.length > 0) {
    const sorted = [...eligible].sort((a, b) => {
      if (a.runtime_increase_pct !== b.runtime_increase_pct) {
        return a.runtime_increase_pct - b.runtime_increase_pct;
      }
      return b.energy_reduction_pct - a.energy_reduction_pct;
    });
    return { matchedPoint: sorted[0], isAchievable: true };
  }
  const sorted = [...curve.frontier_points].sort((a, b) => b.energy_reduction_pct - a.energy_reduction_pct);
  return { matchedPoint: sorted[0], isAchievable: false };
}

function formatConfigDesc(p: AutoPilotCurvePoint): string {
  const parts: string[] = [];
  const cfg = p.configuration || {};
  if (cfg.freq_cap_khz) {
    parts.push(`${(cfg.freq_cap_khz / 1000).toFixed(0)} MHz Cap`);
  } else if (cfg.policy_freq_caps_khz && Object.keys(cfg.policy_freq_caps_khz).length > 0) {
    const val = Object.values(cfg.policy_freq_caps_khz)[0] as number;
    parts.push(`${(val / 1000).toFixed(0)} MHz Cap`);
  } else if (cfg.boost === false) {
    parts.push('2.00 GHz Base');
  } else if (cfg.boost === true) {
    parts.push('5.09 GHz Stock Boost');
  }

  if (cfg.boost === false && !parts.some((s) => s.includes('Base'))) {
    parts.push('Boost Off');
  }
  if (cfg.worker_count) {
    parts.push(`${cfg.worker_count} Cores`);
  }
  return parts.length > 0 ? parts.join(' • ') : p.config_id;
}

export const AutoPilotControl: React.FC<AutoPilotControlProps> = ({
  compact = true,
  onStatusChange,
}) => {
  const { themeColors } = useTheme();
  const c = themeColors;

  const [status, setStatus] = useState<AutoPilotStatus | null>(null);
  const [curves, setCurves] = useState<AutoPilotCurveOption[]>([]);
  const [selectedCurveId, setSelectedCurveId] = useState<string>('');
  const [targetSavings, setTargetSavings] = useState<number>(25);
  const [loading, setLoading] = useState<boolean>(false);
  const [showPopover, setShowPopover] = useState<boolean>(false);
  const popoverRef = useRef<HTMLDivElement>(null);

  // Load available calibration curves
  const loadCurves = useCallback(async () => {
    try {
      const opts = await fetchAutoPilotCurveOptions();
      setCurves(opts);
      if (opts.length > 0 && !selectedCurveId) {
        const defaultCurve = opts.find((o) => o.is_default) || opts[0];
        setSelectedCurveId(defaultCurve.experiment_id);
      }
    } catch (e) {
      console.warn('Failed to load curve options:', e);
    }
  }, [selectedCurveId]);

  // Sync status
  const refreshStatus = useCallback(async () => {
    try {
      const st = await fetchAutoPilotStatus();
      setStatus(st);
      if (st.enabled) {
        if (st.curve_experiment_id) {
          setSelectedCurveId(st.curve_experiment_id);
        }
        if (st.target_savings_pct != null) {
          setTargetSavings(st.target_savings_pct);
        }
      }
      if (onStatusChange) onStatusChange(st);
    } catch {
      // Ignore background poll errors
    }
  }, [onStatusChange]);

  useEffect(() => {
    loadCurves();
    refreshStatus();
    const interval = setInterval(refreshStatus, 2000);
    return () => clearInterval(interval);
  }, [loadCurves, refreshStatus]);

  // Click outside to close popover in compact mode
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setShowPopover(false);
      }
    };
    if (showPopover) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [showPopover]);

  const currentCurve = useMemo(() => {
    return curves.find((crv) => crv.experiment_id === selectedCurveId) || curves[0] || null;
  }, [curves, selectedCurveId]);

  const matchResult = useMemo(() => {
    if (!currentCurve) return null;
    return matchFrontierPoint(currentCurve, targetSavings);
  }, [currentCurve, targetSavings]);

  const matchedPoint = matchResult?.matchedPoint || null;
  const isTargetAchievable = matchResult?.isAchievable ?? true;

  const handleToggle = async () => {
    try {
      setLoading(true);
      if (status?.enabled) {
        await disarmAutoPilot();
      } else {
        await armAutoPilot({
          objective: 'custom_curve',
          experiment_id: selectedCurveId || undefined,
          target_savings_pct: targetSavings,
        });
      }
      await refreshStatus();
    } catch (e) {
      console.error('Failed to toggle Auto-Pilot:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleApplyCurveSettings = async (newTarget?: number, newCurveId?: string) => {
    const target = newTarget !== undefined ? newTarget : targetSavings;
    const curveId = newCurveId !== undefined ? newCurveId : selectedCurveId;
    if (newTarget !== undefined) setTargetSavings(target);
    if (newCurveId !== undefined) setSelectedCurveId(curveId);

    if (status?.enabled) {
      try {
        setLoading(true);
        await armAutoPilot({
          objective: 'custom_curve',
          experiment_id: curveId || undefined,
          target_savings_pct: target,
        });
        await refreshStatus();
      } catch (e) {
        console.error('Failed to update Auto-Pilot settings:', e);
      } finally {
        setLoading(false);
      }
    }
  };

  const isArmed = status?.enabled ?? false;
  const isClamped = isArmed && status?.control_state === 'optimized_active';

  // Compact Navbar Mode
  if (compact) {
    const activeSavingsDisplay = isArmed
      ? status?.empirical_savings_pct != null
        ? `${status.empirical_savings_pct.toFixed(0)}%`
        : `${status?.target_savings_pct ?? targetSavings}%`
      : `${targetSavings}%`;

    return (
      <div style={{ display: 'inline-flex', alignItems: 'center', position: 'relative' }} ref={popoverRef}>
        <button
          type="button"
          onClick={handleToggle}
          disabled={loading}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            padding: '3px 9px',
            borderRadius: radii.md,
            border: `1px solid ${
              isClamped
                ? 'rgba(16, 185, 129, 0.6)'
                : isArmed
                  ? 'rgba(16, 185, 129, 0.35)'
                  : c.border
            }`,
            background: isClamped
              ? 'rgba(16, 185, 129, 0.22)'
              : isArmed
                ? 'rgba(16, 185, 129, 0.10)'
                : c.surfaceElevated,
            color: isClamped
              ? '#10b981'
              : isArmed
                ? c.emerald
                : c.textTertiary,
            fontSize: 11,
            fontWeight: 600,
            cursor: loading ? 'wait' : 'pointer',
            fontFamily: fonts.mono,
            fontFeatureSettings: fontFeatures,
            boxShadow: isClamped ? '0 0 10px rgba(16, 185, 129, 0.45)' : 'none',
            transition: 'all 0.2s ease',
            userSelect: 'none',
          }}
          title={
            isClamped
              ? `Auto-Pilot ACTIVE: Workload clamped to curve Pareto sweet-spot (-${activeSavingsDisplay} Joules, ${status?.current_power_w ?? '?'} W). Restores stock boost at idle.`
              : isArmed
                ? `Auto-Pilot ARMED: Monitoring system power at 100% Stock Boost. Will clamp sustained spikes to target -${activeSavingsDisplay} Joules. Click to disarm.`
                : 'Auto-Pilot OFF: Click to enable autonomous curve-driven sweet-spot clamping.'
          }
        >
          <span
            style={{
              width: 7,
              height: 7,
              borderRadius: '50%',
              backgroundColor: isClamped ? '#10b981' : isArmed ? '#10b981' : c.textQuaternary,
              boxShadow: isClamped ? '0 0 6px #10b981' : 'none',
              animation: isClamped ? 'pulse 1.2s infinite' : 'none',
            }}
          />
          <span>
            {isClamped
              ? `Auto-Pilot: CLAMPED (-${activeSavingsDisplay})`
              : isArmed
                ? `Auto-Pilot: -${activeSavingsDisplay}`
                : 'Auto-Pilot: OFF'}
          </span>
        </button>

        {/* Quick Settings Trigger */}
        <button
          type="button"
          id="autopilot-settings-trigger"
          onClick={() => setShowPopover((prev) => !prev)}
          style={{
            marginLeft: 3,
            padding: '3px 6px',
            borderRadius: radii.md,
            border: `1px solid ${c.border}`,
            background: c.surfaceElevated,
            color: c.textSecondary,
            fontSize: 10,
            cursor: 'pointer',
            fontFamily: fonts.mono,
            display: 'inline-flex',
            alignItems: 'center',
            gap: 2,
          }}
          title="Configure Auto-Pilot Curve & Target Savings"
        >
          <span>⚙️</span>
          <span style={{ fontSize: 8, opacity: 0.7 }}>▼</span>
        </button>

        {/* Compact Settings Popover */}
        {showPopover && (
          <div
            id="autopilot-popover-menu"
            style={{
              position: 'absolute',
              top: '100%',
              right: 0,
              marginTop: 6,
              background: c.panel,
              border: `1px solid ${c.border}`,
              borderRadius: radii.md,
              boxShadow: '0 8px 24px rgba(0, 0, 0, 0.4)',
              padding: '12px',
              zIndex: 9999,
              minWidth: 280,
              display: 'flex',
              flexDirection: 'column',
              gap: 10,
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: c.textPrimary }}>
                Auto-Pilot Target Policy
              </span>
              <span style={{ fontSize: 10, color: c.emerald, fontWeight: 600, fontFamily: fonts.mono }}>
                Target: {targetSavings}%
              </span>
            </div>

            {/* Curve Selector */}
            {curves.length > 0 && (
              <div>
                <div style={{ fontSize: 10, color: c.textTertiary, marginBottom: 3 }}>
                  CALIBRATION CURVE
                </div>
                <select
                  value={selectedCurveId}
                  onChange={(e) => handleApplyCurveSettings(undefined, e.target.value)}
                  style={{
                    width: '100%',
                    padding: '4px 6px',
                    borderRadius: radii.sm,
                    border: `1px solid ${c.border}`,
                    background: c.surfaceElevated,
                    color: c.textPrimary,
                    fontSize: 11,
                    fontFamily: fonts.mono,
                  }}
                >
                  {curves.map((crv) => (
                    <option key={crv.experiment_id} value={crv.experiment_id}>
                      {crv.title}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Slider */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: c.textSecondary, marginBottom: 2 }}>
                <span>Target Energy Savings</span>
                <span style={{ fontWeight: 600, color: c.emerald }}>{targetSavings}%</span>
              </div>
              <input
                type="range"
                min="5"
                max="50"
                step="1"
                value={targetSavings}
                onChange={(e) => handleApplyCurveSettings(Number(e.target.value), undefined)}
                style={{ width: '100%', accentColor: '#10b981', cursor: 'pointer' }}
              />
            </div>

            {/* Live Tradeoff Line */}
            {matchedPoint && (
              <div
                style={{
                  background: 'rgba(16, 185, 129, 0.08)',
                  border: '1px solid rgba(16, 185, 129, 0.25)',
                  borderRadius: radii.sm,
                  padding: '6px 8px',
                  fontSize: 10,
                  fontFamily: fonts.mono,
                  color: c.textSecondary,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 2,
                }}
              >
                <div style={{ color: c.emerald, fontWeight: 600 }}>
                  Empirical: -{matchedPoint.energy_reduction_pct.toFixed(1)}% Joules
                </div>
                <div>
                  Stretch: {matchedPoint.runtime_increase_pct >= 0 ? '+' : ''}{matchedPoint.runtime_increase_pct.toFixed(1)}% time
                  {matchedPoint.avg_power_w ? ` • ${matchedPoint.avg_power_w} W` : ''}
                </div>
              </div>
            )}

            <button
              type="button"
              onClick={handleToggle}
              style={{
                padding: '5px 10px',
                borderRadius: radii.sm,
                border: `1px solid ${isArmed ? '#ef4444' : c.emerald}`,
                background: isArmed ? 'rgba(239, 68, 68, 0.15)' : 'rgba(16, 185, 129, 0.18)',
                color: isArmed ? '#ef4444' : c.emerald,
                fontSize: 11,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              {isArmed ? '⏹ Disarm Auto-Pilot' : '▶ Arm Auto-Pilot'}
            </button>
          </div>
        )}
      </div>
    );
  }

  // Standalone Card Mode (Dashboard)
  return (
    <div
      style={{
        background: c.surface,
        border: `1px solid ${isArmed ? 'rgba(16, 185, 129, 0.35)' : c.border}`,
        borderRadius: radii.lg,
        padding: '1.25rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '1.25rem',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: '1.25rem' }}>🤖</span>
            <span style={{ ...type.h2, fontWeight: 700, color: c.textPrimary, margin: 0 }}>
              Curve-Driven Auto-Pilot
            </span>
            <span
              style={{
                fontSize: '0.75rem',
                fontWeight: 600,
                fontFamily: fonts.mono,
                padding: '2px 8px',
                borderRadius: radii.full,
                background: isClamped
                  ? 'rgba(16, 185, 129, 0.25)'
                  : isArmed
                    ? 'rgba(16, 185, 129, 0.15)'
                    : 'rgba(255, 255, 255, 0.08)',
                color: isArmed ? c.emerald : c.textTertiary,
                border: `1px solid ${isArmed ? 'rgba(16, 185, 129, 0.4)' : c.border}`,
              }}
            >
              {isClamped ? '🌿 ACTIVELY CLAMPED' : isArmed ? '🟢 ARMED (STOCK BOOST IDLE)' : '⚡ OFF'}
            </span>
          </div>
          <p style={{ ...type.small, color: c.textSecondary, margin: '6px 0 0 0', maxWidth: '680px' }}>
            Passively monitors package power at <strong>100% Stock Boost (5.09 GHz)</strong> for everyday snappiness.
            When sustained compile or heavy compute begins (&gt;2s), Auto-Pilot engages the measured Pareto curve below to
            deliver your exact target savings with the minimal possible compute stretch, restoring boost immediately at idle.
          </p>
        </div>

        <button
          type="button"
          onClick={handleToggle}
          disabled={loading}
          style={{
            padding: '8px 18px',
            borderRadius: radii.md,
            border: `1px solid ${isArmed ? '#ef4444' : c.emerald}`,
            background: isArmed ? 'rgba(239, 68, 68, 0.12)' : 'rgba(16, 185, 129, 0.18)',
            color: isArmed ? '#ef4444' : c.emerald,
            fontSize: '0.85rem',
            fontWeight: 600,
            cursor: loading ? 'wait' : 'pointer',
            transition: 'all 0.15s ease',
            userSelect: 'none',
          }}
        >
          {loading ? 'Updating…' : isArmed ? '⏹ Disarm Auto-Pilot' : '▶ Arm Auto-Pilot'}
        </button>
      </div>

      {/* Curve Selector */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ ...type.micro, color: c.textTertiary, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Measured Workload Calibration Curve
          </span>
          {currentCurve && (
            <span style={{ fontSize: '0.75rem', fontFamily: fonts.mono, color: c.textTertiary }}>
              Baseline: {currentCurve.baseline.median_runtime_s}s • {currentCurve.baseline.median_energy_j} J ({currentCurve.baseline.avg_power_w} W)
            </span>
          )}
        </div>
        <select
          value={selectedCurveId}
          onChange={(e) => handleApplyCurveSettings(undefined, e.target.value)}
          style={{
            padding: '8px 12px',
            borderRadius: radii.md,
            border: `1px solid ${c.border}`,
            background: c.surfaceElevated,
            color: c.textPrimary,
            fontSize: '0.85rem',
            fontFamily: fonts.mono,
          }}
        >
          {curves.map((crv) => (
            <option key={crv.experiment_id} value={crv.experiment_id}>
              {crv.title} — max {crv.max_savings_pct.toFixed(1)}% savings
            </option>
          ))}
        </select>
      </div>

      {/* Target Savings Slider & Presets */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, background: c.surfaceElevated, padding: '14px', borderRadius: radii.md, border: `1px solid ${c.border}` }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontWeight: 600, fontSize: '0.9rem', color: c.textPrimary }}>
            Target Energy Savings: <span style={{ color: c.emerald, fontFamily: fonts.mono }}>{targetSavings}%</span>
          </span>
          <span style={{ fontSize: '0.75rem', color: c.textTertiary }}>
            Range: 5% – 50% Joules
          </span>
        </div>

        <input
          type="range"
          min="5"
          max="50"
          step="1"
          value={targetSavings}
          onChange={(e) => handleApplyCurveSettings(Number(e.target.value), undefined)}
          style={{ width: '100%', accentColor: '#10b981', cursor: 'pointer', margin: '4px 0' }}
        />

        {/* Preset Chips */}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 4 }}>
          {[
            { label: '15% Eco-Lite', val: 15, hint: 'Minimal latency impact' },
            { label: '25% Sweet Spot', val: 25, hint: 'Optimal compile efficiency' },
            { label: '35% Deep Eco', val: 35, hint: 'High battery conservation' },
            ...(currentCurve ? [{ label: `Max Frontier (${currentCurve.max_savings_pct.toFixed(0)}%)`, val: Math.round(currentCurve.max_savings_pct), hint: 'Maximum efficiency' }] : []),
          ].map((chip) => {
            const active = targetSavings === chip.val;
            return (
              <button
                key={chip.label}
                type="button"
                onClick={() => handleApplyCurveSettings(chip.val, undefined)}
                style={{
                  padding: '4px 10px',
                  borderRadius: radii.full,
                  border: `1px solid ${active ? c.emerald : c.border}`,
                  background: active ? 'rgba(16, 185, 129, 0.15)' : c.surface,
                  color: active ? c.emerald : c.textSecondary,
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
                title={chip.hint}
              >
                {chip.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Live Tradeoff Preview Card */}
      {matchedPoint && currentCurve && (
        <div
          style={{
            background: 'rgba(16, 185, 129, 0.04)',
            border: '1px solid rgba(16, 185, 129, 0.3)',
            borderRadius: radii.md,
            padding: '14px',
            display: 'flex',
            flexDirection: 'column',
            gap: 10,
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ ...type.micro, color: c.emerald, fontWeight: 700, letterSpacing: '0.5px' }}>
              EXACT EMPIRICAL TRADEOFF PREVIEW (FROM MEASURED HARDWARE DATA)
            </span>
            <span style={{ fontSize: '0.75rem', color: c.textTertiary, fontFamily: fonts.mono }}>
              Config: {matchedPoint.config_id}
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12 }}>
            <div>
              <div style={{ ...type.micro, color: c.textTertiary }}>ENERGY SAVED</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: c.emerald, fontFamily: fonts.mono }}>
                -{matchedPoint.energy_reduction_pct.toFixed(1)}%
              </div>
              <div style={{ fontSize: 11, color: c.textTertiary }}>
                {matchedPoint.median_energy_j.toFixed(1)} J (vs {currentCurve.baseline.median_energy_j.toFixed(1)} J stock)
              </div>
            </div>

            <div>
              <div style={{ ...type.micro, color: c.textTertiary }}>COMPUTE TIME STRETCH</div>
              <div
                style={{
                  fontSize: 18,
                  fontWeight: 700,
                  color: matchedPoint.runtime_increase_pct > 15 ? '#f59e0b' : c.textPrimary,
                  fontFamily: fonts.mono,
                }}
              >
                {matchedPoint.runtime_increase_pct >= 0 ? '+' : ''}
                {matchedPoint.runtime_increase_pct.toFixed(1)}%
              </div>
              <div style={{ fontSize: 11, color: c.textTertiary }}>
                {matchedPoint.median_runtime_s.toFixed(2)}s (vs {currentCurve.baseline.median_runtime_s.toFixed(2)}s stock)
              </div>
            </div>

            <div>
              <div style={{ ...type.micro, color: c.textTertiary }}>AVERAGE CLAMPED POWER</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: c.textPrimary, fontFamily: fonts.mono }}>
                {matchedPoint.avg_power_w != null ? `${matchedPoint.avg_power_w} W` : '—'}
              </div>
              <div style={{ fontSize: 11, color: c.textTertiary }}>
                Stock baseline: {currentCurve.baseline.avg_power_w != null ? `${currentCurve.baseline.avg_power_w} W` : '—'}
              </div>
            </div>

            <div>
              <div style={{ ...type.micro, color: c.textTertiary }}>HARDWARE CLOCK CAP</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: c.textPrimary, fontFamily: fonts.mono, marginTop: 4 }}>
                {formatConfigDesc(matchedPoint)}
              </div>
              <div style={{ fontSize: 11, color: c.textTertiary }}>
                Restores 5.09 GHz boost at idle
              </div>
            </div>
          </div>

          {!isTargetAchievable && (
            <div style={{ fontSize: 11, color: '#f59e0b', background: 'rgba(245, 158, 11, 0.1)', padding: '6px 10px', borderRadius: radii.sm }}>
              ⚠️ Desired target ({targetSavings}%) exceeds curve Pareto frontier. Matched to maximal achievable efficiency point (-{matchedPoint.energy_reduction_pct.toFixed(1)}%).
            </div>
          )}
        </div>
      )}

      {/* Live Telemetry Bar */}
      {isArmed && (
        <div style={{ display: 'flex', gap: '1.25rem', flexWrap: 'wrap', paddingTop: '0.75rem', borderTop: `1px solid ${c.borderSubtle}` }}>
          <div>
            <div style={{ ...type.micro, color: c.textTertiary }}>LIVE PACKAGE POWER</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: c.textPrimary, fontFamily: fonts.mono }}>
              {status?.current_power_w != null ? `${status.current_power_w} W` : 'Measuring…'}
            </div>
          </div>
          <div>
            <div style={{ ...type.micro, color: c.textTertiary }}>IDLE BASELINE</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: c.textPrimary, fontFamily: fonts.mono }}>
              {status?.baseline_w != null ? `${status.baseline_w.toFixed(2)} W` : 'Estimating…'}
            </div>
          </div>
          <div>
            <div style={{ ...type.micro, color: c.textTertiary }}>SPIKE THRESHOLD</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: c.textPrimary, fontFamily: fonts.mono }}>
              {status?.threshold_w != null ? `${status.threshold_w} W` : 'Calibrating…'}
            </div>
          </div>
          <div>
            <div style={{ ...type.micro, color: c.textTertiary }}>SESSIONS OPTIMIZED</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: c.emerald, fontFamily: fonts.mono }}>
              {status?.active_sessions_count ?? 0}
            </div>
          </div>
          <div>
            <div style={{ ...type.micro, color: c.textTertiary }}>TOTAL ENERGY SAVED</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: c.emerald, fontFamily: fonts.mono }}>
              {status?.total_saved_j ? `${status.total_saved_j} J` : '0 J'}
            </div>
          </div>
        </div>
      )}

      {/* Latest Savings Receipt */}
      {status?.latest_savings && (
        <div
          style={{
            padding: '8px 12px',
            borderRadius: radii.sm,
            background: c.surfaceElevated,
            border: `1px solid ${c.border}`,
            fontSize: '0.75rem',
            fontFamily: fonts.mono,
            color: c.textSecondary,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span>
            🎉 Last Burst Saved: <strong style={{ color: c.emerald }}>{status.latest_savings.saved_energy_j} J (-{status.latest_savings.saved_pct}%)</strong>
          </span>
          <span style={{ color: c.textTertiary }}>
            Duration: {status.latest_savings.runtime_s}s • Session #{status.latest_savings.session_id}
          </span>
        </div>
      )}
    </div>
  );
};
