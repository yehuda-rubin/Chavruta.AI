import type { Config } from "tailwindcss";

// The exact design tokens from the static UI (app/frontend/public/ui/tailwind.config.cjs) — same
// colours and fonts, so the Next.js app renders identically.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1c1a17",
        tekhelet: "#002045",
        "tekhelet-2": "#1a365d",
        indigo: "#3a5ba0",
        gold: "#8a6510",
        "gold-soft": "#b88f2e",
        cream: "#fdfbf6",
        "cream-2": "#f6f1e7",
        line: "#ece2cf",
      },
      fontFamily: {
        serif: ['"Frank Ruhl Libre"', "serif"],
        sans: ["Heebo", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
