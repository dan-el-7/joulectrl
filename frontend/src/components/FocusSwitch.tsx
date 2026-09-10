import React from 'react';
import { fonts, fontFeatures, radii } from '../design';
import { useTheme } from '../ThemeContext';

export type FocusMode = 'reverse' | 'off' | 'on';

export interface FocusSwitchProps {
  value: FocusMode;
  onChange: (mode: FocusMode) => void;
  disabled?: boolean;
  size?: 'sm' | 'md';
  showDescription?: boolean;
  feedbackText?: string | null;
}

export const FocusSwitch: React.FC<FocusSwitchProps> = ({
  value,
  onChange,
  disabled = false,
  size = 'sm',
  showDescription = false,
  feedbackText,
}) => {
  const { themeColors } = useTheme();

  const options: {
    id: FocusMode;
    label: string;
    icon: string;
    color: string;
    activeBg: string;
    tooltip: string;
    desc: string;
  }[] = [
    {
      id: 'reverse',
      label: 'Reverse',
      icon: '🔄',
      color: '#10b981', // Emerald / Eco
      activeBg: 'rgba(16, 185, 129, 0.18)',
      tooltip: 'Reverse Focus: Deprioritize target app over running foreground apps (e.g. gaming). Runs on Eco cores with Nice +15.',
      desc: 'Target app deprioritized to Eco cores (Nice +15). Fast cores reserved for foreground games/apps.',
    },
    {
      id: 'off',
      label: 'Off',
      icon: '⚪',
      color: themeColors.textSecondary,
      activeBg: 'rgba(255, 255, 255, 0.10)',
      tooltip: 'Focus Off: Standard balanced OS scheduling across all 16 cores.',
      desc: 'Standard balanced scheduling across all 16 cores.',
    },
    {
      id: 'on',
      label: 'On',
      icon: '🎯',
      color: '#818cf8', // Indigo / Accent
      activeBg: 'rgba(129, 140, 248, 0.20)',
      tooltip: 'Focus On: Pinned task boosted on Zen 5 Fast cores with maximum priority to finish in time.',
      desc: 'Pinned task boosted on Zen 5 Fast cores. Strict deadline prioritization.',
    },
  ];

  const isSmall = size === 'sm';

  return (
    <div style={{ display: 'inline-flex', flexDirection: 'column', gap: 4 }}>
      <div
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          background: themeColors.surfaceElevated,
          border: `1px solid ${themeColors.border}`,
          borderRadius: radii.md,
          padding: 2,
          gap: 2,
          opacity: disabled ? 0.5 : 1,
        }}
        title="Focus Switch: Reverse (deprioritize for gaming/foreground) | Off (standard) | On (sacrifice all to finish in time)"
      >
        <span
          style={{
            padding: isSmall ? '2px 6px' : '4px 8px',
            fontSize: isSmall ? 10 : 11,
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            color: themeColors.textTertiary,
            fontFamily: fonts.mono,
            userSelect: 'none',
          }}
        >
          Focus:
        </span>

        {options.map((opt) => {
          const isActive = value === opt.id;
          return (
            <button
              key={opt.id}
              type="button"
              disabled={disabled}
              onClick={() => onChange(opt.id)}
              title={opt.tooltip}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                padding: isSmall ? '3px 8px' : '5px 12px',
                fontSize: isSmall ? 11 : 12,
                fontWeight: isActive ? 600 : 400,
                color: isActive ? opt.color : themeColors.textTertiary,
                background: isActive ? opt.activeBg : 'transparent',
                border: isActive ? `1px solid ${opt.color}40` : '1px solid transparent',
                borderRadius: radii.sm,
                cursor: disabled ? 'not-allowed' : 'pointer',
                transition: 'all 0.15s ease',
                outline: 'none',
                fontFamily: fonts.sans,
                fontFeatureSettings: fontFeatures,
              }}
            >
              <span style={{ fontSize: isSmall ? 10 : 12 }}>{opt.icon}</span>
              <span>{opt.label}</span>
            </button>
          );
        })}
      </div>

      {showDescription && (
        <div style={{ fontSize: 11, color: themeColors.textTertiary, marginTop: 2 }}>
          {options.find((o) => o.id === value)?.desc}
        </div>
      )}

      {feedbackText && (
        <div style={{ fontSize: 11, color: '#10b981', fontWeight: 500, marginTop: 2 }}>
          {feedbackText}
        </div>
      )}
    </div>
  );
};
