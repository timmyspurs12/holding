import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        obsidian: "#0A0B0D",
        ink: "#111317",
        ink2: "#16181D",
        paper: "#F3F0E8",
        warm: "#FAF9F5",
        stone: "#A7A39A",
        muted: "#686A67",
        copper: "#D7A45A",
        verdict: "#9FBF9A",
        dissent: "#C96B62",
        info: "#7D9CB8",
      },
      fontFamily: {
        display: ["var(--font-display)", "Georgia", "serif"],
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
      },
      fontSize: {
        "2xs": ["10px", "1.4"],
        xs2: ["11px", "1.45"],
      },
      letterSpacing: { label: "0.16em" },
      maxWidth: { shell: "1240px" },
      transitionTimingFunction: {
        precise: "cubic-bezier(0.16, 1, 0.3, 1)",
      },
      keyframes: {
        draw: { "0%": { strokeDashoffset: "100" }, "100%": { strokeDashoffset: "0" } },
        riseIn: { "0%": { opacity: "0", transform: "translateY(6px)" }, "100%": { opacity: "1", transform: "translateY(0)" } },
        pulseSoft: { "0%,100%": { opacity: "0.35" }, "50%": { opacity: "1" } },
        shimmer: { "0%": { transform: "translateX(-100%)" }, "100%": { transform: "translateX(100%)" } },
      },
      animation: {
        riseIn: "riseIn 400ms cubic-bezier(0.16, 1, 0.3, 1) both",
        pulseSoft: "pulseSoft 2.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
export default config;
