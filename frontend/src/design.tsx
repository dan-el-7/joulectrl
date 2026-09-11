/*
 * Single source of truth for the joulectrl dashboard's design language.
 *
 * Inspired by Aceternity UI & Linear's design system:
 * High-contrast dark instrument mode alongside an elegant, crisp slate & zinc light mode.
 * Information density managed through clear luminance hierarchy, semi-transparent frosted borders,
 * reserved chromatic accents, and monospace values for hardware metrics.
 */

import React from 'react';

export type ThemeMode = 'dark' | 'light';

export interface ThemeColors {
  bg: string;
  panel: string;
  surface: string;
  surfaceElevated: string;
  surfaceHover: string;
  textPrimary: string;
  textSecondary: string;
  textTertiary: string;
  textQuaternary: string;
  border: string;
  borderSubtle: string;
  accent: string;
  accentHover: string;
  accentBg: string;
  accentDim: string;
  cardShadow: string;
  inputBg: string;
  inputBorder: string;
  green: string;
  emerald: string;
  amber: string;
  red: string;
  /** Semantic tints — theme-aware so light mode never renders white-on-white. */
  tint: {
    /** faint neutral fill (replaces rgba(255,255,255,0.02–0.08)) */
    neutral: string;
    /** slightly stronger neutral fill */
    neutralStrong: string;
    /** success / selected fill (emerald family) */
    success: string;
    /** success border */
    successBorder: string;
    /** danger / stop fill (red family) */
    danger: string;
    /** danger border */
    dangerBorder: string;
    /** warning fill (amber family) */
    warning: string;
    /** info / running fill (cyan family) */
    info: string;
    /** info border */
    infoBorder: string;
    /** accent fill (indigo family) */
    accentSoft: string;
    /** strong overlay for popovers in the current theme */
    overlay: string;
    /** popover / dropdown shadow */
    popoverShadow: string;
  };
  series: {
    fast: string;
    efficient: string;
    accent2: string;
    neutral: string;
    warn: string;
  };
}

export const DARK_THEME: ThemeColors = {
  bg: '#08090a',
  panel: '#0f1011',
  surface: '#141516',
  surfaceElevated: '#191a1b',
  surfaceHover: 'rgba(255, 255, 255, 0.04)',
  textPrimary: '#f7f8f8',
  textSecondary: '#d0d6e0',
  textTertiary: '#8a8f98',
  textQuaternary: '#62666d',
  border: 'rgba(255, 255, 255, 0.08)',
  borderSubtle: 'rgba(255, 255, 255, 0.05)',
  accent: '#7170ff',
  accentHover: '#828fff',
  accentBg: '#5e6ad2',
  accentDim: 'rgba(113, 112, 255, 0.12)',
  cardShadow: '0 2px 4px rgba(0, 0, 0, 0.3)',
  inputBg: '#18191a',
  inputBorder: 'rgba(255, 255, 255, 0.12)',
  green: '#27a644',
  emerald: '#10b981',
  amber: '#f59e0b',
  red: '#f4586e',
  tint: {
    neutral: 'rgba(255, 255, 255, 0.03)',
    neutralStrong: 'rgba(255, 255, 255, 0.07)',
    success: 'rgba(16, 185, 129, 0.14)',
    successBorder: 'rgba(16, 185, 129, 0.45)',
    danger: 'rgba(244, 88, 110, 0.14)',
    dangerBorder: 'rgba(244, 88, 110, 0.45)',
    warning: 'rgba(245, 158, 11, 0.12)',
    info: 'rgba(34, 211, 238, 0.12)',
    infoBorder: 'rgba(34, 211, 238, 0.4)',
    accentSoft: 'rgba(113, 112, 255, 0.14)',
    overlay: 'rgba(4, 4, 6, 0.7)',
    popoverShadow: '0 8px 24px rgba(0, 0, 0, 0.45)',
  },
  series: {
    fast: '#7170ff',
    efficient: '#10b981',
    accent2: '#828fff',
    neutral: '#8a8f98',
    warn: '#f59e0b',
  },
};

export const LIGHT_THEME: ThemeColors = {
  bg: '#f8fafc',
  panel: '#ffffff',
  surface: '#ffffff',
  surfaceElevated: '#f1f5f9',
  surfaceHover: 'rgba(0, 0, 0, 0.03)',
  textPrimary: '#0f172a',
  textSecondary: '#334155',
  textTertiary: '#64748b',
  textQuaternary: '#94a3b8',
  border: '#e2e8f0',
  borderSubtle: '#f1f5f9',
  accent: '#6366f1',
  accentHover: '#4f46e5',
  accentBg: '#6366f1',
  accentDim: 'rgba(99, 102, 241, 0.12)',
  cardShadow: '0 1px 3px rgba(0, 0, 0, 0.07), 0 1px 2px rgba(0, 0, 0, 0.04)',
  inputBg: '#ffffff',
  inputBorder: '#cbd5e1',
  green: '#16a34a',
  emerald: '#059669',
  amber: '#d97706',
  red: '#dc2626',
  tint: {
    neutral: 'rgba(15, 23, 42, 0.035)',
    neutralStrong: 'rgba(15, 23, 42, 0.07)',
    success: 'rgba(5, 150, 105, 0.10)',
    successBorder: 'rgba(5, 150, 105, 0.45)',
    danger: 'rgba(220, 38, 38, 0.08)',
    dangerBorder: 'rgba(220, 38, 38, 0.40)',
    warning: 'rgba(217, 119, 6, 0.10)',
    info: 'rgba(6, 182, 212, 0.10)',
    infoBorder: 'rgba(6, 182, 212, 0.4)',
    accentSoft: 'rgba(99, 102, 241, 0.10)',
    overlay: 'rgba(15, 23, 42, 0.45)',
    popoverShadow: '0 8px 24px rgba(15, 23, 42, 0.18)',
  },
  series: {
    fast: '#6366f1',
    efficient: '#059669',
    accent2: '#4f46e5',
    neutral: '#64748b',
    warn: '#d97706',
  },
};

export const getThemeColors = (theme: ThemeMode = 'dark'): ThemeColors => {
  return theme === 'light' ? LIGHT_THEME : DARK_THEME;
};

let _activeTheme: ThemeMode =
  typeof window !== 'undefined' && localStorage.getItem('joulectrl_theme') === 'light'
    ? 'light'
    : 'dark';

export const setActiveTheme = (theme: ThemeMode) => {
  _activeTheme = theme;
};

export const getActiveTheme = (): ThemeMode => _activeTheme;

/**
 * Dynamic proxy for `colors`. Reads directly from the currently active theme,
 * enabling seamless instant theming even in legacy components without props changes.
 */
export const colors: ThemeColors = new Proxy({} as ThemeColors, {
  get: (_target, prop: string | symbol) => {
    const current = getThemeColors(_activeTheme);
    return (current as any)[prop];
  },
  ownKeys: () => Reflect.ownKeys(getThemeColors(_activeTheme)),
  getOwnPropertyDescriptor: (_target, prop) =>
    Reflect.getOwnPropertyDescriptor(getThemeColors(_activeTheme), prop),
});

export const fonts = {
  sans: "'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif",
  mono: "'JetBrains Mono', ui-monospace, 'Cascadia Mono', 'Consolas', monospace",
} as const;

export const fontFeatures = "'cv01', 'ss03'";

export const type = {
  display: { fontSize: 28, fontWeight: 510, letterSpacing: '-0.6px', lineHeight: 1.1 },
  h1: { fontSize: 20, fontWeight: 590, letterSpacing: '-0.24px', lineHeight: 1.33 },
  h2: { fontSize: 16, fontWeight: 590, letterSpacing: '-0.1px', lineHeight: 1.4 },
  body: { fontSize: 14, fontWeight: 400, lineHeight: 1.5 },
  small: { fontSize: 13, fontWeight: 400, letterSpacing: '-0.13px', lineHeight: 1.5 },
  smallMedium: { fontSize: 13, fontWeight: 510, letterSpacing: '-0.13px', lineHeight: 1.5 },
  caption: { fontSize: 12, fontWeight: 400, lineHeight: 1.5 },
  label: { fontSize: 11, fontWeight: 510, lineHeight: 1.4 },
  micro: { fontSize: 11, fontWeight: 510, lineHeight: 1.4 },
  monoValue: { fontSize: 13, fontWeight: 500, lineHeight: 1.4 },
  monoLabel: { fontSize: 11, fontWeight: 400, lineHeight: 1.4 },
} as const;

export const radii = { xs: 2, sm: 4, md: 6, lg: 8, xl: 12, full: 9999 } as const;

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 } as const;

export const getCardStyle = (theme: ThemeMode = _activeTheme): React.CSSProperties => {
  const c = getThemeColors(theme);
  return {
    background: c.surface,
    border: `1px solid ${c.border}`,
    borderRadius: radii.lg,
    boxShadow: c.cardShadow,
    color: c.textPrimary,
  };
};

export const getSubtleCardStyle = (theme: ThemeMode = _activeTheme): React.CSSProperties => {
  const c = getThemeColors(theme);
  return {
    background: theme === 'light' ? '#f8fafc' : 'rgba(255,255,255,0.02)',
    border: `1px solid ${c.borderSubtle}`,
    borderRadius: radii.lg,
    color: c.textPrimary,
  };
};

export const getPanelButtonStyle = (theme: ThemeMode = _activeTheme): React.CSSProperties => {
  const c = getThemeColors(theme);
  return {
    background: theme === 'light' ? '#f1f5f9' : 'rgba(255,255,255,0.02)',
    color: c.textSecondary,
    border: `1px solid ${c.border}`,
    borderRadius: radii.md,
    cursor: 'pointer',
    font: 'inherit',
  };
};

// Dynamic Proxies for standard shared style objects so { ...card } adapts automatically
export const card: React.CSSProperties = new Proxy({} as React.CSSProperties, {
  get: (_target, prop: string | symbol) => {
    return (getCardStyle(_activeTheme) as any)[prop];
  },
  ownKeys: () => Reflect.ownKeys(getCardStyle(_activeTheme)),
  getOwnPropertyDescriptor: (_target, prop) =>
    Reflect.getOwnPropertyDescriptor(getCardStyle(_activeTheme), prop),
});

export const subtleCard: React.CSSProperties = new Proxy({} as React.CSSProperties, {
  get: (_target, prop: string | symbol) => {
    return (getSubtleCardStyle(_activeTheme) as any)[prop];
  },
  ownKeys: () => Reflect.ownKeys(getSubtleCardStyle(_activeTheme)),
  getOwnPropertyDescriptor: (_target, prop) =>
    Reflect.getOwnPropertyDescriptor(getSubtleCardStyle(_activeTheme), prop),
});

export const panelButton: React.CSSProperties = new Proxy({} as React.CSSProperties, {
  get: (_target, prop: string | symbol) => {
    return (getPanelButtonStyle(_activeTheme) as any)[prop];
  },
  ownKeys: () => Reflect.ownKeys(getPanelButtonStyle(_activeTheme)),
  getOwnPropertyDescriptor: (_target, prop) =>
    Reflect.getOwnPropertyDescriptor(getPanelButtonStyle(_activeTheme), prop),
});

export const primaryButton: React.CSSProperties = {
  background: '#6366f1',
  color: '#ffffff',
  border: 'none',
  borderRadius: radii.md,
  cursor: 'pointer',
  font: 'inherit',
  fontWeight: 510,
};

export const ghostButton: React.CSSProperties = new Proxy({} as React.CSSProperties, {
  get: (_target, prop: string | symbol) => {
    const c = getThemeColors(_activeTheme);
    const base: React.CSSProperties = {
      background: 'transparent',
      color: c.textSecondary,
      border: `1px solid ${c.border}`,
      borderRadius: radii.md,
      cursor: 'pointer',
      font: 'inherit',
      fontWeight: 510,
    };
    return (base as any)[prop];
  },
  ownKeys: () => Reflect.ownKeys(getPanelButtonStyle(_activeTheme)),
  getOwnPropertyDescriptor: (_target, prop) =>
    Reflect.getOwnPropertyDescriptor(getPanelButtonStyle(_activeTheme), prop),
});

export const focusRing = {
  outline: 'none',
  ':focus-visible': {
    boxShadow: `0 0 0 2px #6366f1`,
  },
} as const;

/* --------------------------------------------------------------------------- */
/* Icon system — 14×14 stroke SVG glyphs, currentColor, no emoji.              */
/* One <Icon name="stop" /> instead of a dozen ad-hoc emoji spans.            */
/* --------------------------------------------------------------------------- */

export type IconName =
  | 'stop'
  | 'sun'
  | 'moon'
  | 'gear'
  | 'chevronDown'
  | 'play'
  | 'warn'
  | 'check'
  | 'star'
  | 'leaf'
  | 'bolt'
  | 'clock'
  | 'shield'
  | 'trash'
  | 'reset'
  | 'terminal'
  | 'target'
  | 'refresh'
  | 'ban';

const ICON_PATHS: Record<IconName, string> = {
  stop: '<rect x="3.5" y="3.5" width="7" height="7" rx="1.2" fill="currentColor" stroke="none"/>',
  sun: '<circle cx="7" cy="7" r="2.6"/><path d="M7 .8v1.7M7 11.5v1.7M.8 7h1.7M11.5 7h1.7M2.6 2.6l1.2 1.2M10.2 10.2l1.2 1.2M11.4 2.6l-1.2 1.2M3.8 10.2l-1.2 1.2"/>',
  moon: '<path d="M11.5 8.8A5 5 0 0 1 5.2 2.5a5 5 0 1 0 6.3 6.3Z"/>',
  gear: '<circle cx="7" cy="7" r="1.8"/><path d="M7 1.6v1.6M7 9.8v2.6M2.9 3.9l1.2 1.2M9.9 9.9l1.2 1.2M1.6 7h1.6M9.8 7h2.6M2.9 10.1l1.2-1.2M9.9 4.1l1.2-1.2"/>',
  chevronDown: '<path d="m3.5 5.5 3.5 3.5 3.5-3.5"/>',
  play: '<path d="M4 2.8v8.4c0 .6.7 1 1.2.7l6.6-4.2c.5-.3.5-1 0-1.3L5.2 2.1c-.5-.3-1.2.1-1.2.7Z" fill="currentColor" stroke="none"/>',
  warn: '<path d="M7 1.8 13 12H1L7 1.8Z"/><path d="M7 5.5v3"/><circle cx="7" cy="10.6" r="0.7" fill="currentColor" stroke="none"/>',
  check: '<path d="m2.5 7.3 3 3 6-6.6"/>',
  star: '<path d="m7 1.8 1.7 3.6 3.9.5-2.9 2.7.8 3.9L7 10.5l-3.5 2 .8-3.9-2.9-2.7 3.9-.5L7 1.8Z"/>',
  leaf: '<path d="M11.5 2.5C6 2.5 2.5 5.5 2.5 9.5c0 1 .3 1.8.8 2.4C5 9 7.5 7.5 10.5 6.8 8 8.6 5.8 10.6 4.3 13c.8.4 1.7.5 2.7.5 4 0 6-4.5 4.5-11Z"/>',
  bolt: '<path d="M8 1 3 8h3.5L6 13l5-7H7.5L8 1Z"/>',
  clock: '<circle cx="7" cy="7" r="5.2"/><path d="M7 3.8V7l2.4 1.6"/>',
  shield: '<path d="M7 1.5 12 3.4c0 4.4-1.8 8-5 9.6-3.2-1.6-5-5.2-5-9.6L7 1.5Z"/>',
  trash: '<path d="M2.5 4h9M5.5 4V2.5h3V4M4 4l.5 8.5h5L10 4M6 6.5v4M8 6.5v4"/>',
  reset: '<path d="M2.8 7a4.2 4.2 0 1 1 1.3 3"/><path d="M2.8 10.5V7h3.5" transform="translate(-1.5 -1.5)"/>',
  terminal: '<rect x="1.8" y="2.5" width="10.4" height="9" rx="1.5"/><path d="m4.2 6 2 2-2 2M7.8 10h3"/>',
  target: '<circle cx="7" cy="7" r="5"/><circle cx="7" cy="7" r="2.4"/><circle cx="7" cy="7" r="0.6" fill="currentColor" stroke="none"/>',
  refresh: '<path d="M12 7A5 5 0 1 1 9.5 2.8"/><path d="M9.5 0.8v2.4h2.4"/>',
  ban: '<circle cx="7" cy="7" r="5"/><path d="m3.5 3.5 7 7"/>',
};

export const Icon: React.FC<{
  name: IconName;
  size?: number;
  color?: string;
  style?: React.CSSProperties;
  title?: string;
}> = ({ name, size = 14, color, style, title }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 14 14"
    fill="none"
    stroke={color ?? 'currentColor'}
    strokeWidth={1.4}
    strokeLinecap="round"
    strokeLinejoin="round"
    style={{ flexShrink: 0, ...style }}
    aria-hidden={title ? undefined : true}
    role={title ? 'img' : undefined}
  >
    {title ? <title>{title}</title> : null}
    <g dangerouslySetInnerHTML={{ __html: ICON_PATHS[name] }} />
  </svg>
);

export const sectionLabel: React.CSSProperties = new Proxy({} as React.CSSProperties, {
  get: (_target, prop: string | symbol) => {
    const c = getThemeColors(_activeTheme);
    const base: React.CSSProperties = {
      ...type.micro,
      textTransform: 'uppercase',
      letterSpacing: '0.08em',
      color: c.textTertiary,
    };
    return (base as any)[prop];
  },
  ownKeys: () => ['fontSize', 'fontWeight', 'lineHeight', 'textTransform', 'letterSpacing', 'color'],
  getOwnPropertyDescriptor: (_target, prop) => {
    const c = getThemeColors(_activeTheme);
    const base: React.CSSProperties = {
      ...type.micro,
      textTransform: 'uppercase',
      letterSpacing: '0.08em',
      color: c.textTertiary,
    };
    return Reflect.getOwnPropertyDescriptor(base, prop);
  },
});
