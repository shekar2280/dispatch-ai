export const THEME_COLORS = {
  ink: '#0D2622',
  ink2: '#143530',
  paper: '#F1F4EE',
  wash: '#E3EBE0',
  leaf: '#1E6B56',
  mint: '#BFDDCD',
  sun: '#F4B63A',
  line: 'rgba(13, 38, 34, 0.16)',
  lineLight: 'rgba(13, 38, 34, 0.08)',
  white: '#FFFFFF',
  cardBg: '#FFFFFF',
  cardBorder: 'rgba(13, 38, 34, 0.12)',
  mutedText: 'rgba(13, 38, 34, 0.65)',
  accentGold: '#F4B63A',
} as const;

export type ThemeColors = typeof THEME_COLORS;
