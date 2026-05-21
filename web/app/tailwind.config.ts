import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx,js,jsx,mdx}",
    "./components/**/*.{ts,tsx,js,jsx,mdx}",
    "./lib/**/*.{ts,tsx,js,jsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          5: "var(--ink-5)",
          10: "var(--ink-10)",
          40: "var(--ink-40)",
          80: "var(--ink-80)",
          100: "var(--ink-100)",
        },
        cyan: "var(--cyan)",
        violet: "var(--violet)",
        magenta: "var(--magenta)",
        lime: "var(--lime)",
        "ts-red": "var(--ts-red)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "var(--font-sans)", "serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
