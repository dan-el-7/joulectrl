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
  micro: { fontSize: 10, fontWeight: 510, lineHeight: 1.4 },
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
