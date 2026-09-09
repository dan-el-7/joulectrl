import React from 'react';
import { colors, fonts, fontFeatures, type, radii, sectionLabel } from '../design';

interface NavbarProps {
  activeTab: 'setup' | 'explorer' | 'calibration' | 'validation' | 'watch';
  onSelectTab: (tab: 'setup' | 'explorer' | 'calibration' | 'validation' | 'watch') => void;
  restorationStatus: string;
  onEmergencyRestore: () => void;
  isRestoring: boolean;
  experimentState?: string | null;
  experimentStateMessage?: string | null;
}

const TABS = [
  { id: 'setup', label: 'Setup' },
  { id: 'explorer', label: 'Profile' },
  { id: 'calibration', label: 'Calibration' },
  { id: 'validation', label: 'Validation' },
  { id: 'watch', label: 'Watch' },
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
}) => {
  const restored = restorationStatus === 'restored' || restorationStatus === 'not_required';
  const isRunning = !!experimentState && RUNNING_STATES[experimentState] !== undefined;
  const stateLabel = experimentState
    ? RUNNING_STATES[experimentState] ?? experimentState.replace('_', ' ').toLowerCase()
    : null;

  return (
    <header
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 20px',
        height: 48,
        backgroundColor: colors.panel,
        borderBottom: `1px solid ${colors.borderSubtle}`,
        position: 'sticky',
        top: 0,
        zIndex: 50,
        fontFeatureSettings: fontFeatures,
        fontFamily: fonts.sans,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
        {/* wordmark */}
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 7 }}>
          <span style={{ ...type.h2, color: colors.textPrimary, letterSpacing: '-0.3px' }}>
            joulectrl
          </span>
          <span style={{ ...type.micro, color: colors.textQuaternary, fontFamily: fonts.mono }}>
            v0.2
          </span>
        </div>

        {/* tabs */}
        <nav style={{ display: 'flex', gap: 2, height: '100%' }}>
          {TABS.map((item) => {
            const active = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onSelectTab(item.id)}
                style={{
                  ...type.smallMedium,
                  padding: '0 10px',
                  height: '100%',
                  border: 'none',
                  borderBottom: `2px solid ${active ? colors.accent : 'transparent'}`,
                  backgroundColor: 'transparent',
                  color: active ? colors.textPrimary : colors.textTertiary,
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
        {/* live experiment state — running indicator */}
        {stateLabel && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 7,
              padding: '3px 10px',
              borderRadius: radii.full,
              border: `1px solid ${isRunning ? colors.accentDim : colors.border}`,
              background: isRunning ? 'rgba(113,112,255,0.08)' : 'transparent',
              ...type.micro,
              color: isRunning ? colors.accentHover : colors.textSecondary,
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
                  backgroundColor: colors.accentHover,
                  animation: 'jc-pulse 1.2s ease-in-out infinite',
                }}
              />
            ) : (
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  backgroundColor: experimentState === 'COMPLETE' ? colors.emerald : colors.amber,
                }}
              />
            )}
            {stateLabel}
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
            border: `1px solid ${colors.border}`,
            ...type.micro,
            color: colors.textSecondary,
            fontFamily: fonts.mono,
          }}
          title={`Restoration state: ${restorationStatus}`}
        >
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              backgroundColor: restored ? colors.emerald : colors.amber,
              boxShadow: `0 0 6px ${restored ? colors.emerald : colors.amber}`,
            }}
          />
          {restorationStatus.replace('_', ' ')}
        </div>

        <button
          onClick={onEmergencyRestore}
          disabled={isRestoring}
          style={{
            ...type.label,
            padding: '5px 12px',
            background: 'rgba(255,255,255,0.03)',
            color: isRestoring ? colors.textTertiary : colors.textSecondary,
            border: `1px solid ${colors.border}`,
            borderRadius: radii.md,
            cursor: isRestoring ? 'wait' : 'pointer',
            font: 'inherit',
            fontSize: 11,
          }}
          title="Emergency restoration of CPU and power settings"
        >
          {isRestoring ? 'Restoring…' : 'Restore'}
        </button>
      </div>
    </header>
  );
};
