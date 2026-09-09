import React from 'react';
import { colors, fonts, fontFeatures, type, radii, sectionLabel } from '../design';

interface NavbarProps {
  activeTab: 'setup' | 'explorer' | 'calibration' | 'validation' | 'watch';
  onSelectTab: (tab: 'setup' | 'explorer' | 'calibration' | 'validation' | 'watch') => void;
  restorationStatus: string;
  onEmergencyRestore: () => void;
  isRestoring: boolean;
}

const TABS = [
  { id: 'setup', label: 'Setup' },
  { id: 'explorer', label: 'Profile' },
  { id: 'calibration', label: 'Calibration' },
  { id: 'validation', label: 'Validation' },
  { id: 'watch', label: 'Watch' },
] as const;

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  onSelectTab,
  restorationStatus,
  onEmergencyRestore,
  isRestoring,
}) => {
  const restored = restorationStatus === 'restored' || restorationStatus === 'not_required';

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
