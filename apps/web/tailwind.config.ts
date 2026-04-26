import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
    "./hooks/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        reactor:   "#38e8ff",
        plasma:    "#ff3f81",
        ambercore: "#ffd166",
        void:      "#04060a",
      },
      fontFamily: {
        sans:  ["var(--font-space-grotesk)", "system-ui", "sans-serif"],
        mono:  ["var(--font-jb-mono)", "ui-monospace", "monospace"],
      },
      boxShadow: {
        hud:  "0 0 28px rgba(56, 232, 255, 0.18)",
        core: "0 0 80px rgba(56, 232, 255, 0.45)",
      },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to:   { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.3s ease-out both",
      },
    },
  },
  plugins: [],
};

export default config;
