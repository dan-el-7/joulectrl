/*
 * Single source of truth for the joulectrl dashboard's design language.
 *
 * Inspired by Linear's design system: darkness as the native medium, information
 * density managed through luminance steps rather than color, one reserved
 * chromatic accent, whisper-thin semi-transparent borders, and a monospace
 * companion for measured values. A measurement tool should look like an
 * instrument, not a marketing page.
 */

export const colors = {
  /* surfaces — luminance stack, deepest to most elevated */
  bg: '#08090a',            // page canvas
  panel: '#0f1011',         // header, sidebar
  surface: '#141516',       // cards
  surfaceElevated: '#191a1b',
  surfaceHover: 'rgba(255,255,255,0.04)',

  /* text — never pure white */
  textPrimary: '#f7f8f8',
  textSecondary: '#d0d6e0',
  textTertiary: '#8a8f98',
  textQuaternary: '#62666d',

  /* borders — semi-transparent white only */
  border: 'rgba(255,255,255,0.08)',
  borderSubtle: 'rgba(255,255,255,0.05)',

  /* the single accent — reserved for interaction + selection */
  accent: '#7170ff',
  accentHover: '#828fff',
  accentBg: '#5e6ad2',
  accentDim: 'rgba(113,112,255,0.12)',

  /* semantic — used only for status, never decoratively */
  green: '#27a644',
  emerald: '#10b981',
  amber: '#f59e0b',
  red: '#f4586e',

  /* data series — cool, distinguishable on dark, colorblind-considerate */
  series: {
    fast: '#7170ff',        // accent violet for the fast class
    efficient: '#10b981',   // emerald for the efficient class
    accent2: '#828fff',
    neutral: '#8a8f98',
    warn: '#f59e0b',
  },
} as const;

export const fonts = {
  sans: "'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif",
  mono: "'JetBrains Mono', ui-monospace, 'Cascadia Mono', 'Consolas', monospace",
} as const;

export const fontFeatures = "'cv01', 'ss03'";

/* type scale — sizes in px, weights from Linear's three-tier system */
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

/* shared style objects — use with spread */
export const card: React.CSSProperties = {
  background: colors.surface,
  border: `1px solid ${colors.border}`,
  borderRadius: radii.lg,
};

export const subtleCard: React.CSSProperties = {
  background: 'rgba(255,255,255,0.02)',
  border: `1px solid ${colors.borderSubtle}`,
  borderRadius: radii.lg,
};

export const panelButton: React.CSSProperties = {
  background: 'rgba(255,255,255,0.02)',
  color: colors.textSecondary,
  border: `1px solid ${colors.border}`,
  borderRadius: radii.md,
  cursor: 'pointer',
  font: 'inherit',
};

export const primaryButton: React.CSSProperties = {
  background: colors.accentBg,
  color: '#ffffff',
  border: 'none',
  borderRadius: radii.md,
  cursor: 'pointer',
  font: 'inherit',
  fontWeight: 510,
};

export const ghostButton: React.CSSProperties = {
  background: 'transparent',
  color: colors.textSecondary,
  border: `1px solid ${colors.border}`,
  borderRadius: radii.md,
  cursor: 'pointer',
  font: 'inherit',
  fontWeight: 510,
};

/* small helpers */
export const focusRing = {
  outline: 'none',
  ':focus-visible': {
    boxShadow: `0 0 0 2px ${colors.accent}`,
  },
} as const;

/* label style for tiny uppercase section markers */
export const sectionLabel: React.CSSProperties = {
  ...type.micro,
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
  color: colors.textTertiary,
};
