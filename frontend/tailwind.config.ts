import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      spacing: {
        '1': '4px',
        '2': '8px',
        '3': '12px',
        '4': '16px',
        '5': '20px',
        '6': '24px',
        '8': '32px',
        '10': '40px',
        '12': '48px',
        '16': '64px',
        '20': '80px',
        '24': '96px',
      },
      colors: {
        gray: {
          950: '#0a0a0f',
          900: '#111118',
          800: '#1a1a24',
          700: '#252535',
          600: '#3a3a50',
          500: '#5a5a78',
          400: '#8080a0',
          300: '#a0a0c0',
          200: '#c0c0d8',
          100: '#e0e0f0',
        },
      },
    },
  },
  plugins: [],
}

export default config
