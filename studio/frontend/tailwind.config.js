/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "#f4f6f8",
          raised: "#ffffff",
          sunk: "#e8ecf0",
        },
        ink: {
          DEFAULT: "#1a2332",
          muted: "#5a6577",
          faint: "#8a94a6",
        },
        line: {
          DEFAULT: "#d0d7e0",
          strong: "#a8b3c2",
        },
        accent: {
          DEFAULT: "#0b6e4f",
          soft: "#d8f0e6",
          muted: "#3d8b6e",
        },
        warn: {
          DEFAULT: "#b45309",
          soft: "#fef3c7",
        },
        danger: {
          DEFAULT: "#b91c1c",
          soft: "#fee2e2",
        },
        highlight: {
          DEFAULT: "#1d4ed8",
          soft: "#dbeafe",
        },
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
      },
      boxShadow: {
        panel: "0 1px 0 rgba(26, 35, 50, 0.06)",
      },
    },
  },
  plugins: [],
};
