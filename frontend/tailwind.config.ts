import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        voyager: {
          navy: 'rgb(var(--voyager-navy) / <alpha-value>)', navy2: 'rgb(var(--voyager-navy2) / <alpha-value>)', surface: 'rgb(var(--voyager-surface) / <alpha-value>)', surface2: 'rgb(var(--voyager-surface2) / <alpha-value>)',
          blue: 'rgb(var(--voyager-blue) / <alpha-value>)', 'blue-light': 'rgb(var(--voyager-blue-light) / <alpha-value>)', 'blue-glow': 'rgb(var(--voyager-blue) / .15)',
          success: 'rgb(var(--voyager-success) / <alpha-value>)', warning: 'rgb(var(--voyager-warning) / <alpha-value>)', critical: 'rgb(var(--voyager-critical) / <alpha-value>)',
          'text-primary': 'rgb(var(--voyager-text-primary) / <alpha-value>)', 'text-secondary': 'rgb(var(--voyager-text-secondary) / <alpha-value>)', 'text-muted': 'rgb(var(--voyager-text-muted) / <alpha-value>)',
          border: 'rgb(var(--voyager-border) / .15)', 'border-strong': 'rgb(var(--voyager-border) / .3)',
        },
      },
      fontFamily: { display: ['Space Grotesk', 'Inter', 'system-ui', 'sans-serif'], mono: ['JetBrains Mono', 'ui-monospace', 'monospace'] },
      boxShadow: { glow: '0 0 32px rgba(14, 165, 233, 0.16)' },
    },
  },
  plugins: [],
} satisfies Config;
