/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Goose Brand Colors
        'block-teal': '#13bbaf',
        'block-orange': '#ff4f00',
        
        // Neutral Palette
        neutral: {
          50: '#f4f6f7',
          100: '#e3e6ea',
          200: '#c5c9cf',
          300: '#9da4ad',
          400: '#737982',
          500: '#5b6169',
          600: '#4a4e55',
          700: '#3b3e44',
          800: '#2c2e33',
          900: '#1a1b1e',
          950: '#0d0e10',
        },
        
        // Status Colors
        red: {
          50: '#ffe5e5',
          100: '#ff6b6b',
          400: '#f87171',
          500: '#ef4444',
          600: '#dc2626',
        },
        blue: {
          50: '#e7f0ff',
          100: '#7cacff',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
        },
        green: {
          50: '#e8f5e9',
          100: '#a3d795',
          400: '#4ade80',
          500: '#22c55e',
          600: '#16a34a',
        },
        yellow: {
          50: '#fff9e6',
          100: '#ffd966',
          400: '#facc15',
          500: '#eab308',
          600: '#ca8a04',
        },
        purple: {
          50: '#f3e8ff',
          100: '#c084fc',
          400: '#a855f7',
          500: '#9333ea',
          600: '#7e22ce',
        },
        
        // Semantic Colors - Light Mode
        background: {
          default: 'var(--background-default)',
          muted: 'var(--background-muted)',
          medium: 'var(--background-medium)',
          strong: 'var(--background-strong)',
        },
        border: {
          default: 'var(--border-default)',
          input: 'var(--border-input)',
          focus: 'var(--border-focus)',
        },
        text: {
          default: 'var(--text-default)',
          muted: 'var(--text-muted)',
          accent: 'var(--text-accent)',
        },
        
        primary: 'var(--color-primary)',
        accent: 'var(--color-accent)',
        
        // Workflow-specific colors
        node: {
          entry: 'var(--color-node-entry)',
          exit: 'var(--color-node-exit)',
          llm: 'var(--color-node-llm)',
          code: 'var(--color-node-code)',
          control: 'var(--color-node-control)',
          api: 'var(--color-node-api)',
          data: 'var(--color-node-data)',
        },
        edge: {
          default: 'var(--color-edge-default)',
          selected: 'var(--color-edge-selected)',
          hover: 'var(--color-edge-hover)',
        },
      },
      
      boxShadow: {
        xs: 'var(--shadow-xs)',
        sm: 'var(--shadow-sm)',
        md: 'var(--shadow-md)',
        lg: 'var(--shadow-lg)',
        xl: 'var(--shadow-xl)',
      },
      
      animation: {
        easeG2: 'cubic-bezier(0.55, 0, 1, 0.45)',
      }
    },
  },
  plugins: [],
}