import React from 'react';
import { fetchSystemThermal, SystemThermalStatus } from '../api';
import { getThemeColors, fonts, fontFeatures, type, radii, ThemeMode } from '../design';
import { FocusSwitch, FocusMode } from './FocusSwitch';
import { AutoPilotControl } from './AutoPilotControl';

interface NavbarProps {
  activeTab: 'setup' | 'explorer' | 'calibration' | 'validation' | 'demo' | 'watch' | 'tasks' | 'dashboard' | 'settings';
  onSelectTab: (tab: 'setup' | 'explorer' | 'calibration' | 'validation' | 'demo' | 'watch' | 'tasks' | 'dashboard' | 'settings') => void;
  restorationStatus: string;
  onEmergencyRestore: () => void;
  isRestoring: boolean;
  experimentState?: string | null;
  experimentStateMessage?: string | null;
  runProgress?: { index: number; total: number; configId?: string } | null;
  experiments?: any[];
  currentExperimentId?: string;
  onSelectExperiment?: (id: string) => void;
  onCancelExperiment?: () => void;
  theme?: ThemeMode;
  onToggleTheme?: () => void;
  focusMode?: FocusMode;
  onChangeFocusMode?: (mode: FocusMode) => void;
}

const TABS = [
  { id: 'setup', label: 'Setup' },
  { id: 'explorer', label: 'Profile' },
  { id: 'calibration', label: 'Calibration' },
  { id: 'validation', label: 'Validation' },
  { id: 'demo', label: 'Demo' },
  { id: 'watch', label: 'Watch' },
  { id: 'tasks', label: 'Tasks' },
  { id: 'dashboard', label: '🌱 Savings' },
  { id: 'settings', label: 'Settings' },
] as const;

/** Terminal states — experiment finished, no longer "running". */
const TERMINAL_STATES = new Set(['COMPLETE', 'FAILED', 'RESTORED', 'RECOVERY_REQUIRED', 'IDLE']);

/** Running states get a live pulsing dot + spinner text. */
const RUNNING_STATES: Record<string, string> = {
  CHECKING: 'Checking machine…',
  PREPARING: 'Preparing…',
  PROFILING: 'Profiling — measuring…',
  PROFILE_READY: 'Selecting configuration…',
  SELECTED: 'Awaiting validation…',
  VALIDATING: 'Validating — measuring…',
  RESTORING: 'Restoring settings…',
  CANCELLING: 'Cancelling…',
};

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  onSelectTab,
  restorationStatus,
  onEmergencyRestore,
  isRestoring,
  experimentState,
  experimentStateMessage,
  runProgress,
  experiments,
  currentExperimentId,
  onSelectExperiment,
  onCancelExperiment,
  theme = 'dark',
  onToggleTheme,
  focusMode = 'off',
  onChangeFocusMode,
}) => {
  const c = getThemeColors(theme);
  const restored = restorationStatus === 'restored' || restorationStatus === 'not_required';
  const isRunning = !!experimentState && RUNNING_STATES[experimentState] !== undefined;
  const stateLabel = experimentState
    ? RUNNING_STATES[experimentState] ?? experimentState.replace('_', ' ').toLowerCase()
    : null;

  const [thermal, setThermal] = React.useState<SystemThermalStatus | null>(null);

  React.useEffect(() => {
    let active = true;
    const checkThermal = () => {
      fetchSystemThermal()
        .then((th) => {
          if (active) setThermal(th);
        })
        .catch(() => {});
    };
    checkThermal();
    const interval = setInterval(checkThermal, 4000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <header
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 20px',
        height: 48,
        backgroundColor: c.panel,
        borderBottom: `1px solid ${c.borderSubtle}`,
        position: 'sticky',
        top: 0,
        zIndex: 50,
        fontFeatureSettings: fontFeatures,
        fontFamily: fonts.sans,
        transition: 'background-color 0.2s ease, border-color 0.2s ease',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
        {/* wordmark */}
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 7 }}>
          <span style={{ ...type.h2, color: c.textPrimary, letterSpacing: '-0.3px' }}>
            joulectrl
          </span>
          <span style={{ ...type.micro, color: c.textQuaternary, fontFamily: fonts.mono }}>
            v0.2
          </span>
        </div>

        {/* tabs */}
        <nav style={{ display: 'flex', gap: 2, height: '100%' }}>
          {TABS.map((item) => {
            const active = activeTab === item.id;
            return (
              <button
                id={`nav-tab-${item.id}`}
                key={item.id}
                onClick={() => onSelectTab(item.id)}
                style={{
                  ...type.smallMedium,
                  padding: '0 10px',
                  height: '100%',
                  border: 'none',
                  borderBottom: `2px solid ${active ? c.accent : 'transparent'}`,
                  backgroundColor: 'transparent',
                  color: active ? c.textPrimary : c.textTertiary,
                  cursor: 'pointer',
                  transition: 'color 0.15s ease',
                }}
              >
                {item.label}
              </button>
            );
          })}
        </nav>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        {/* run progress — N of M during profiling */}
        {runProgress && runProgress.total > 0 && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '3px 10px',
              borderRadius: radii.full,
              border: `1px solid ${c.border}`,
              ...type.micro,
              color: c.textSecondary,
              fontFamily: fonts.mono,
            }}
            title={runProgress.configId ? `Measuring: ${runProgress.configId}` : 'Measuring'}
          >
            <span>
              run {runProgress.index}/{runProgress.total}
            </span>
            <span
              style={{
                width: 64,
                height: 4,
                borderRadius: radii.full,
                background: c.borderSubtle,
                overflow: 'hidden',
                display: 'inline-block',
              }}
            >
              <span
                style={{
                  display: 'block',
                  width: `${Math.round((runProgress.index / runProgress.total) * 100)}%`,
                  height: '100%',
                  background: c.accentHover,
                  transition: 'width 0.3s ease',
                }}
              />
            </span>
          </div>
        )}

        {/* live experiment state — running indicator */}
        {stateLabel && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 7,
              padding: '3px 10px',
              borderRadius: radii.full,
              border: `1px solid ${isRunning ? c.accentDim : c.border}`,
              background: isRunning ? (theme === 'light' ? 'rgba(99,102,241,0.1)' : 'rgba(113,112,255,0.08)') : 'transparent',
              ...type.micro,
              color: isRunning ? c.accentHover : c.textSecondary,
              fontFamily: fonts.mono,
            }}
            title={experimentStateMessage ? `${experimentState}: ${experimentStateMessage}` : `Experiment state: ${experimentState}`}
          >
            {isRunning ? (
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  backgroundColor: c.accentHover,
                  animation: 'jc-pulse 1.2s ease-in-out infinite',
                }}
              />
            ) : (
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  backgroundColor: experimentState === 'COMPLETE' ? c.emerald : c.amber,
                }}
              />
            )}
            {stateLabel}
          </div>
        )}

        {/* Stop Run button */}
        {isRunning && onCancelExperiment && (
          <button
            onClick={onCancelExperiment}
            style={{
              ...type.label,
              padding: '4px 10px',
              background: 'rgba(239, 68, 68, 0.15)',
              color: '#ef4444',
              border: '1px solid rgba(239, 68, 68, 0.45)',
              borderRadius: radii.md,
              cursor: 'pointer',
              font: 'inherit',
              fontSize: 11,
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: 5,
            }}
            title="Stop active profiling / calibration and restore CPU settings immediately"
          >
            <span>⏹</span> Stop Run
          </button>
        )}

        {/* Experiment switcher dropdown */}
        {experiments && experiments.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ ...type.micro, color: c.textTertiary, fontFamily: fonts.mono }}>Exp:</span>
            <select
              value={currentExperimentId || ''}
              onChange={(e) => onSelectExperiment && onSelectExperiment(e.target.value)}
              style={{
                backgroundColor: c.surfaceElevated,
                color: c.textPrimary,
                border: `1px solid ${c.border}`,
                borderRadius: radii.md,
                padding: '2px 8px',
                fontSize: 11,
                fontFamily: fonts.mono,
                cursor: 'pointer',
                maxWidth: '220px',
                outline: 'none',
              }}
            >
              {experiments.map((exp: any) => (
                <option key={exp.id} value={exp.id}>
                  {exp.id.startsWith('exp_') && exp.id.length > 20
                    ? `${exp.workload_id || 'run'} (${exp.created_at ? exp.created_at.slice(11, 19) : exp.id.slice(4, 15)})`
                    : exp.id}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Global Auto-Pilot Mode Switch */}
        <AutoPilotControl compact={true} />

        {/* Focus Switch: reverse (game/foreground priority) | off | on (pinned task priority) */}
        {onChangeFocusMode && (
          <FocusSwitch
            value={focusMode}
            onChange={onChangeFocusMode}
            size="sm"
          />
        )}

        {/* Thermal / Throttling live indicator */}
        {thermal && thermal.cpu_temp_c !== null && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 5,
              padding: '3px 8px',
              borderRadius: radii.full,
              border: `1px solid ${
                thermal.warning_level === 'critical'
                  ? 'rgba(239, 68, 68, 0.5)'
                  : thermal.warning_level === 'elevated'
                    ? 'rgba(245, 158, 11, 0.4)'
                    : c.border
              }`,
              background:
                thermal.warning_level === 'critical'
                  ? 'rgba(239, 68, 68, 0.15)'
                  : thermal.warning_level === 'elevated'
                    ? 'rgba(245, 158, 11, 0.12)'
                    : 'transparent',
              ...type.micro,
              color:
                thermal.warning_level === 'critical'
                  ? '#ef4444'
                  : thermal.warning_level === 'elevated'
                    ? '#f59e0b'
                    : c.textTertiary,
              fontFamily: fonts.mono,
            }}
            title={thermal.message}
          >
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: '50%',
                backgroundColor:
                  thermal.warning_level === 'critical'
                    ? '#ef4444'
                    : thermal.warning_level === 'elevated'
                      ? '#f59e0b'
                      : c.emerald,
              }}
            />
            <span>{thermal.cpu_temp_c.toFixed(0)}°C</span>
            {thermal.warning_level !== 'normal' && (
              <span style={{ fontWeight: 600 }}>
                {thermal.warning_level === 'critical' ? 'THROTTLING' : 'WARM'}
              </span>
            )}
          </div>
        )}

        {/* restoration state — always visible (non-negotiable) */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '3px 10px',
            borderRadius: radii.full,
            border: `1px solid ${c.border}`,
            ...type.micro,
            color: c.textSecondary,
            fontFamily: fonts.mono,
          }}
          title={`Restoration state: ${restorationStatus}`}
        >
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              backgroundColor: restored ? c.emerald : c.amber,
              boxShadow: `0 0 6px ${restored ? c.emerald : c.amber}`,
            }}
          />
          {restorationStatus.replace('_', ' ')}
        </div>

        {/* Emergency restore button */}
        <button
          onClick={onEmergencyRestore}
          disabled={isRestoring}
          style={{
            ...type.label,
            padding: '5px 12px',
            background: theme === 'light' ? '#f1f5f9' : 'rgba(255,255,255,0.03)',
            color: isRestoring ? c.textTertiary : c.textSecondary,
            border: `1px solid ${c.border}`,
            borderRadius: radii.md,
            cursor: isRestoring ? 'wait' : 'pointer',
            font: 'inherit',
            fontSize: 11,
          }}
          title="Emergency restoration of CPU and power settings"
        >
          {isRestoring ? 'Restoring…' : 'Restore'}
        </button>

        {/* Global Light / Dark Theme toggle pill */}
        {onToggleTheme && (
          <button
            onClick={onToggleTheme}
            style={{
              ...type.label,
              padding: '4px 10px',
              background: theme === 'light' ? '#f1f5f9' : 'rgba(255,255,255,0.05)',
              color: c.textPrimary,
              border: `1px solid ${c.border}`,
              borderRadius: radii.md,
              cursor: 'pointer',
              font: 'inherit',
              fontSize: 11,
              fontWeight: 510,
              display: 'flex',
              alignItems: 'center',
              gap: 5,
              transition: 'all 0.15s ease',
            }}
            title={`Switch to ${theme === 'dark' ? 'Light' : 'Dark'} mode`}
          >
            <span>{theme === 'dark' ? '☀️' : '🌙'}</span>
            <span>{theme === 'dark' ? 'Light' : 'Dark'}</span>
          </button>
        )}
      </div>
    </header>
  );
};
