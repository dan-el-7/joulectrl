import React, { useEffect, useState, useCallback, useRef } from 'react';
import { fetchAutoPilotStatus, armAutoPilot, disarmAutoPilot, AutoPilotStatus } from '../api';
import { fonts, fontFeatures, radii, type } from '../design';
import { useTheme } from '../ThemeContext';

export interface AutoPilotControlProps {
  compact?: boolean;
  onStatusChange?: (status: AutoPilotStatus) => void;
}

export const AutoPilotControl: React.FC<AutoPilotControlProps> = ({
  compact = true,
  onStatusChange,
}) => {
  const { themeColors } = useTheme();
  const c = themeColors;

  const [status, setStatus] = useState<AutoPilotStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [selectedObjective, setSelectedObjective] = useState<'efficiency' | 'balanced' | 'performance'>('efficiency');
  const [showObjectiveMenu, setShowObjectiveMenu] = useState<boolean>(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const refreshStatus = useCallback(async () => {
    try {
      const st = await fetchAutoPilotStatus();
      setStatus(st);
      if (st.enabled && st.objective) {
        setSelectedObjective(st.objective);
      }
      if (onStatusChange) onStatusChange(st);
    } catch {
      // Ignore background network blips
    }
  }, [onStatusChange]);

  useEffect(() => {
    refreshStatus();
    const interval = setInterval(refreshStatus, 2000);
    return () => clearInterval(interval);
  }, [refreshStatus]);

  // Click outside to close objective menu
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowObjectiveMenu(false);
      }
    };
    if (showObjectiveMenu) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [showObjectiveMenu]);

  const handleToggle = async () => {
    try {
      setLoading(true);
      if (status?.enabled) {
        await disarmAutoPilot();
      } else {
        await armAutoPilot({ objective: selectedObjective });
      }
      await refreshStatus();
    } catch (e) {
      console.error('Failed to toggle Auto-Pilot:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleChangeObjective = async (obj: 'efficiency' | 'balanced' | 'performance') => {
    setSelectedObjective(obj);
    setShowObjectiveMenu(false);
    if (status?.enabled) {
      try {
        setLoading(true);
        await armAutoPilot({ objective: obj });
        await refreshStatus();
      } catch (e) {
        console.error('Failed to change Auto-Pilot objective:', e);
      } finally {
        setLoading(false);
      }
    }
  };

  const isArmed = status?.enabled ?? false;
  const isClamped = isArmed && status?.control_state === 'optimized_active';
  const isIdle = isArmed && !isClamped;

  const objectiveLabels: Record<'efficiency' | 'balanced' | 'performance', { label: string; desc: string; icon: string }> = {
    efficiency: { label: 'Sweet Spot', desc: 'Clamps to 2.0 GHz base (~30% Joules saved, best for parallel builds)', icon: '🌱' },
    balanced: { label: 'Balanced', desc: 'Clamps to 2.8 GHz (~15-20% saved, minimal runtime stretch)', icon: '⚖️' },
    performance: { label: 'Shield', desc: '100% Stock Boost (5.09 GHz) + Fast Zen 5 core prioritization', icon: '⚡' },
  };

  if (compact) {
    return (
      <div style={{ display: 'inline-flex', alignItems: 'center', position: 'relative' }} ref={menuRef}>
        {/* Toggle Button */}
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
              ? `Auto-Pilot ACTIVE: Workload clamped to ${selectedObjective} sweet spot (${status?.current_power_w ?? '?'} W). Restores stock boost at idle.`
              : isArmed
                ? `Auto-Pilot ARMED: Monitoring system power at 100% Stock Boost. Will clamp sustained compute spikes to ${selectedObjective}. Click to turn off.`
                : 'Auto-Pilot OFF: Click to run autonomous background sweet-spot optimization for heavy workloads.'
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
              ? 'Auto-Pilot: CLAMPED'
              : isArmed
                ? 'Auto-Pilot: ARMED'
                : 'Auto-Pilot: OFF'}
          </span>
        </button>

        {/* Objective Pill / Dropdown Trigger */}
        <button
          type="button"
          onClick={() => setShowObjectiveMenu((prev) => !prev)}
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
            gap: 3,
          }}
          title="Change Auto-Pilot target policy"
        >
          <span>{objectiveLabels[selectedObjective].icon}</span>
          <span>{objectiveLabels[selectedObjective].label}</span>
          <span style={{ fontSize: 8, opacity: 0.7 }}>▼</span>
        </button>

        {/* Objective Dropdown Menu */}
        {showObjectiveMenu && (
          <div
            style={{
              position: 'absolute',
              top: '100%',
              right: 0,
              marginTop: 6,
              background: c.panel,
              border: `1px solid ${c.border}`,
              borderRadius: radii.md,
              boxShadow: '0 8px 24px rgba(0, 0, 0, 0.4)',
              padding: 6,
              zIndex: 100,
              minWidth: 220,
              display: 'flex',
              flexDirection: 'column',
              gap: 4,
            }}
          >
            <div style={{ fontSize: 10, color: c.textTertiary, padding: '2px 8px', fontWeight: 600 }}>
              AUTO-PILOT TARGET POLICY
            </div>
            {(['efficiency', 'balanced', 'performance'] as const).map((key) => {
              const item = objectiveLabels[key];
              const active = selectedObjective === key;
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => handleChangeObjective(key)}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'flex-start',
                    padding: '6px 8px',
                    borderRadius: radii.sm,
                    border: 'none',
                    background: active ? 'rgba(16, 185, 129, 0.15)' : 'transparent',
                    color: active ? c.emerald : c.textPrimary,
                    cursor: 'pointer',
                    textAlign: 'left',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 600 }}>
                    <span>{item.icon}</span>
                    <span>{item.label}</span>
                    {active && <span style={{ fontSize: 10, marginLeft: 'auto' }}>✓</span>}
                  </div>
                  <div style={{ fontSize: 10, color: c.textTertiary, marginTop: 2 }}>{item.desc}</div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  // Standalone Card Mode (for Dashboard)
  return (
    <div
      style={{
        background: c.surface,
        border: `1px solid ${isArmed ? 'rgba(16, 185, 129, 0.35)' : c.border}`,
        borderRadius: radii.lg,
        padding: '1.25rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: '1.25rem' }}>🤖</span>
            <span style={{ ...type.h2, fontWeight: 700, color: c.textPrimary, margin: 0 }}>System-Wide Auto-Pilot</span>
            <span
              style={{
                fontSize: '0.75rem',
                fontWeight: 600,
                fontFamily: fonts.mono,
                padding: '2px 8px',
                borderRadius: radii.full,
                background: isClamped ? 'rgba(16, 185, 129, 0.25)' : isArmed ? 'rgba(16, 185, 129, 0.15)' : 'rgba(255, 255, 255, 0.08)',
                color: isArmed ? c.emerald : c.textTertiary,
                border: `1px solid ${isArmed ? 'rgba(16, 185, 129, 0.4)' : c.border}`,
              }}
            >
              {isClamped ? '🌿 ACTIVELY CLAMPED' : isArmed ? '🟢 ARMED (IDLE)' : '⚡ OFF'}
            </span>
          </div>
          <p style={{ ...type.small, color: c.textSecondary, margin: '6px 0 0 0', maxWidth: '640px' }}>
            Passively monitors CPU package power at zero overhead. Your laptop runs at <strong>100% Stock Boost (5.09 GHz)</strong> for web browsing and UI snappiness. When a sustained compile or compute spike begins (&gt;2s), Auto-Pilot clamps to the Pareto sweet-spot, saving <strong>25%–35% Joules</strong>, and restores boost the moment the build finishes.
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
          {loading ? 'Updating…' : isArmed ? '⏹ Disarm Auto-Pilot' : '▶ Enable Auto-Pilot'}
        </button>
      </div>

      {/* Target Policy Selector */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ ...type.micro, color: c.textTertiary, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
          Target Optimization Policy
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 8 }}>
          {(['efficiency', 'balanced', 'performance'] as const).map((key) => {
            const item = objectiveLabels[key];
            const active = selectedObjective === key;
            return (
              <div
                key={key}
                onClick={() => handleChangeObjective(key)}
                style={{
                  padding: '10px 12px',
                  borderRadius: radii.md,
                  border: `1px solid ${active ? c.emerald : c.border}`,
                  background: active ? 'rgba(16, 185, 129, 0.10)' : c.surfaceElevated,
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontWeight: 600, fontSize: '0.85rem', color: active ? c.emerald : c.textPrimary }}>
                    {item.icon} {item.label}
                  </span>
                  {active && <span style={{ color: c.emerald, fontSize: '0.8rem' }}>● Active</span>}
                </div>
                <div style={{ fontSize: '0.72rem', color: c.textTertiary, marginTop: 4 }}>
                  {item.desc}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Live Metrics row */}
      {isArmed && (
        <div style={{ display: 'flex', gap: '1.25rem', paddingTop: '0.75rem', borderTop: `1px solid ${c.borderSubtle}` }}>
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
    </div>
  );
};
