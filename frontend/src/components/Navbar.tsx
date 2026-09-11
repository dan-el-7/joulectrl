import React from 'react';
import { fetchSystemThermal, SystemThermalStatus } from '../api';
import { colors, getThemeColors, fonts, fontFeatures, type, radii, Icon, ThemeMode } from '../design';
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
  { id: 'dashboard', label: 'Savings' },
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

/** Compact status pill used in the header's top row. */
const StatusPill: React.FC<{
  theme: ThemeMode;
  dotColor: string;
  textColor: string;
  borderColor?: string;
  background?: string;
  pulse?: boolean;
  title?: string;
  children: React.ReactNode;
}> = ({ theme, dotColor, textColor, borderColor, background, pulse, title, children }) => {
  const c = getThemeColors(theme);
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '3px 10px',
        borderRadius: radii.full,
        border: `1px solid ${borderColor ?? c.border}`,
        background: background ?? 'transparent',
        ...type.micro,
        color: textColor,
        fontFamily: fonts.mono,
        whiteSpace: 'nowrap',
      }}
      title={title}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: '50%',
          backgroundColor: dotColor,
          boxShadow: `0 0 6px ${dotColor}`,
          ...(pulse ? { animation: 'jc-pulse 1.2s ease-in-out infinite' } : {}),
        }}
      />
      {children}
    </div>
  );
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
  const stateUpper = (experimentState || '').toUpperCase();
  const isRunning = !!stateUpper && RUNNING_STATES[stateUpper] !== undefined;
  const stateLabel = stateUpper && RUNNING_STATES[stateUpper]
    ? RUNNING_STATES[stateUpper]
    : experimentState
    ? experimentState.replace('_', ' ').toLowerCase()
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
      {/* ---- Row 1: identity · context · safety ---- */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
          padding: '0 20px',
          height: 48,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, minWidth: 0 }}>
          {/* wordmark */}
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 7, flexShrink: 0 }}>
            <span style={{ ...type.h2, color: c.textPrimary, letterSpacing: '-0.3px' }}>
              joulectrl
            </span>
            <span style={{ ...type.micro, color: c.textQuaternary, fontFamily: fonts.mono }}>
              v0.2
            </span>
          </div>

          {/* experiment switcher */}
          {experiments && experiments.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
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
                  maxWidth: '200px',
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
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
          {/* live experiment state */}
          {stateLabel && (
            <StatusPill
              theme={theme}
              dotColor={isRunning ? c.accentHover : experimentState === 'COMPLETE' ? c.emerald : c.amber}
              pulse={isRunning}
              textColor={isRunning ? c.accentHover : c.textSecondary}
              borderColor={isRunning ? undefined : c.border}
              background={isRunning ? c.tint.accentSoft : undefined}
              title={experimentStateMessage ? `${experimentState}: ${experimentStateMessage}` : `Experiment state: ${experimentState}`}
            >
              {stateLabel}
            </StatusPill>
          )}

          {/* thermal */}
          {thermal && thermal.cpu_temp_c !== null && (
            <StatusPill
              theme={theme}
              dotColor={
                thermal.warning_level === 'critical'
                  ? c.red
                  : thermal.warning_level === 'elevated'
                    ? c.amber
                    : c.emerald
              }
              textColor={
                thermal.warning_level === 'critical'
                  ? c.red
                  : thermal.warning_level === 'elevated'
                    ? c.amber
                    : c.textTertiary
              }
              borderColor={
                thermal.warning_level === 'critical'
                  ? c.tint.dangerBorder
                  : thermal.warning_level === 'elevated'
                    ? colors.tint.warning
                    : undefined
              }
              background={
                thermal.warning_level === 'critical'
                  ? c.tint.danger
                  : thermal.warning_level === 'elevated'
                    ? c.tint.warning
                    : undefined
              }
              title={thermal.message}
            >
              <span>{thermal.cpu_temp_c.toFixed(0)}°C</span>
              {thermal.warning_level !== 'normal' && (
                <span style={{ fontWeight: 600 }}>
                  {thermal.warning_level === 'critical' ? 'THROTTLING' : 'WARM'}
                </span>
              )}
            </StatusPill>
          )}

          {/* restoration state — always visible (non-negotiable) */}
          <StatusPill
            theme={theme}
            dotColor={restored ? c.emerald : c.amber}
            textColor={c.textSecondary}
            title={`Restoration state: ${restorationStatus}`}
          >
            {restorationStatus.replace('_', ' ')}
          </StatusPill>

          {/* Stop Run button */}
          {isRunning && onCancelExperiment && (
            <button
              onClick={onCancelExperiment}
              style={{
                ...type.label,
                padding: '4px 10px',
                background: c.tint.danger,
                color: c.red,
                border: `1px solid ${c.tint.dangerBorder}`,
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
              <Icon name="stop" size={11} /> Stop Run
            </button>
          )}

          {/* Emergency restore button */}
          <button
            onClick={onEmergencyRestore}
            disabled={isRestoring}
            style={{
              ...type.label,
              padding: '5px 12px',
              background: theme === 'light' ? c.surfaceElevated : colors.tint.neutralStrong,
              color: isRestoring ? c.textTertiary : c.textSecondary,
              border: `1px solid ${c.border}`,
              borderRadius: radii.md,
              cursor: isRestoring ? 'wait' : 'pointer',
              font: 'inherit',
              fontSize: 11,
              display: 'flex',
              alignItems: 'center',
              gap: 5,
            }}
            title="Emergency restoration of CPU and power settings"
          >
            {isRestoring ? 'Restoring…' : (
              <>
                <Icon name="reset" size={12} /> Restore
              </>
            )}
          </button>

          {/* Light / Dark toggle */}
          {onToggleTheme && (
            <button
              onClick={onToggleTheme}
              style={{
                ...type.label,
                padding: '4px 10px',
                background: theme === 'light' ? c.surfaceElevated : colors.tint.neutral,
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
              <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={13} />
              <span>{theme === 'dark' ? 'Light' : 'Dark'}</span>
            </button>
          )}
        </div>
      </div>

      {/* ---- Row 2: tabs · autopilot · focus ---- */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
          padding: '0 20px',
          height: 40,
          borderTop: `1px solid ${c.borderSubtle}`,
        }}
      >
        <nav style={{ display: 'flex', gap: 2, height: '100%', overflowX: 'auto', minWidth: 0 }} aria-label="Main">
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
                  whiteSpace: 'nowrap',
                }}
              >
                {item.label}
              </button>
            );
          })}
        </nav>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
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
        </div>
      </div>
    </header>
  );
};
