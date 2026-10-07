import type { Config } from "tailwindcss";

// Design tokens for the "Conversation" redesign (violet / mint / coral on a lavender canvas).
// The token NAMES are unchanged (ink, tekhelet, gold, cream, line, indigo) so every component picks
// up the new palette without a rewrite: tekhelet = deep violet for headings and selected fills,
// indigo = the brand violet, gold = the mint accent (text + tints), line = lavender hairline.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1a1633",
        tekhelet: "#2b2170",
        "tekhelet-2": "#3a2d99",
        indigo: "#5b3df5",
        gold: "#0e8f72",
        "gold-soft": "#19c9a0",
        coral: "#ff6b5e",
        sun: "#ffc83d",
        cream: "#f6f4ff",
        "cream-2": "#efeaff",
        line: "#e6e2fa",
      },
      fontFamily: {
        // Rubik carries the whole UI; "serif" now means Rubik too (it was the heading face), and
        // `quote` (Frank Ruhl Libre) is kept for quoted source text so the primary text reads as
        // distinct from the assistant's own voice.
        serif: ["Rubik", "Heebo", "sans-serif"],
        sans: ["Rubik", "Heebo", "sans-serif"],
        quote: ['"Frank Ruhl Libre"', "serif"],
      },
    },
  },
  plugins: [],
};

export default config;
