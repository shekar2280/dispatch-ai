import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        serif: ['Newsreader', 'Georgia', 'serif'],
        sans: ['Plus Jakarta Sans', 'sans-serif'],
      },
      colors: {
        background: "#F1F4EE",
        foreground: "#0D2622",
        ink: {
          DEFAULT: "#0D2622",
          secondary: "#143530",
        },
        ink2: "#143530",
        paper: "#F1F4EE",
        wash: "#E3EBE0",
        leaf: "#1E6B56",
        mint: "#BFDDCD",
        sun: "#F4B63A",
        line: "rgba(13, 38, 34, 0.16)",
        brand: {
          50: "#F1F4EE",
          100: "#E3EBE0",
          200: "#BFDDCD",
          300: "#8FBFA6",
          400: "#47957D",
          500: "#1E6B56",
          600: "#185B49",
          700: "#144B3D",
          800: "#143530",
          900: "#0D2622",
          DEFAULT: "#1E6B56",
          glow: "rgba(244, 182, 58, 0.35)",
        },
        card: {
          DEFAULT: "#FFFFFF",
          border: "rgba(13, 38, 34, 0.12)",
        },
      },
      backdropBlur: {
        xs: "2px",
        glass: "16px",
      },
      animation: {
        'pulse-glow': 'pulseGlow 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'alert-blink': 'alertBlink 1.2s ease-in-out infinite',
      },
      keyframes: {
        pulseGlow: {
          '0%, 100%': { opacity: '1', transform: 'scale(1)' },
          '50%': { opacity: '0.6', transform: 'scale(1.03)' },
        },
        alertBlink: {
          '0%, 100%': { borderColor: 'rgba(223, 208, 184, 0.9)', boxShadow: '0 0 25px rgba(223, 208, 184, 0.45)' },
          '50%': { borderColor: 'rgba(223, 208, 184, 0.25)', boxShadow: '0 0 8px rgba(223, 208, 184, 0.1)' },
        }
      }
    },
  },
  plugins: [],
};

export default config;
