import { join } from 'path';

import { Config } from 'tailwindcss';

module.exports = {
  content: [
    './index.html',
    join(__dirname, 'src/**/*!(*.stories|*.spec).{js,ts,jsx,tsx}'),
    // AppTension's shared primitives (including Dialog) are imported directly from
    // sibling libraries. Include them explicitly so Tailwind emits their utility
    // classes even when Nx's dependency graph doesn't discover a library edge.
    join(__dirname, '../webapp-libs/*/src/**/*.{js,ts,jsx,tsx}'),
    join(__dirname, '../../frontend/src/**/*!(*.stories|*.spec).{js,ts,jsx,tsx}'),
  ],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: 'hsl(var(--background))',
          raised: 'hsl(var(--card))',
          sunk: 'hsl(var(--muted))',
        },
        ink: {
          DEFAULT: 'hsl(var(--foreground))',
          muted: 'hsl(var(--muted-foreground))',
          faint: 'hsl(var(--muted-foreground))',
        },
        line: {
          DEFAULT: 'hsl(var(--border))',
          strong: 'hsl(var(--ring))',
        },
        accent: {
          DEFAULT: 'hsl(var(--primary))',
          soft: 'hsl(var(--accent))',
          muted: 'hsl(var(--muted-foreground))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        warn: {
          DEFAULT: 'hsl(38 92% 42%)',
          soft: 'hsl(48 96% 89%)',
        },
        danger: {
          DEFAULT: 'hsl(var(--destructive))',
          soft: 'hsl(var(--destructive) / 0.12)',
        },
        highlight: {
          DEFAULT: 'hsl(var(--ring))',
          soft: 'hsl(var(--ring) / 0.12)',
        },
      },
      boxShadow: {
        panel: '0 1px 0 rgb(15 23 42 / 0.06)',
      },
    },
  },
  plugins: [],
  presets: [require('../../tailwind.workspace-preset')],
} as Config;
