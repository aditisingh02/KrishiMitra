import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", "Helvetica Neue", "sans-serif"],
        serif: ["var(--font-serif)", "Georgia", "serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      colors: {
        // warm monochrome
        paper: "#FBFBFA",
        bone: "#F7F6F3",
        surface: "#FFFFFF",
        ink: "#1A1A18",
        charcoal: "#2F3437",
        muted: "#787774",
        faint: "#9B9A97",
        line: "#EAEAEA",
        // single restrained brand accent (deep field green)
        field: {
          50: "#EDF3EC",
          600: "#346538",
          700: "#2B5430",
        },
        // washed pastels for tags/semantics
        pale: {
          red: "#FDEBEC",
          redink: "#9F2F2D",
          blue: "#E1F3FE",
          blueink: "#1F6C9F",
          green: "#EDF3EC",
          greenink: "#346538",
          yellow: "#FBF3DB",
          yellowink: "#956400",
        },
      },
      borderRadius: {
        DEFAULT: "6px",
      },
      boxShadow: {
        // ultra-diffuse, low opacity only
        subtle: "0 1px 2px rgba(0,0,0,0.03)",
        lift: "0 2px 12px rgba(0,0,0,0.05)",
      },
      maxWidth: {
        content: "64rem",
      },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(12px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        drift: {
          "0%, 100%": { transform: "translate(0,0)" },
          "50%": { transform: "translate(3%, 4%)" },
        },
        marquee: {
          from: { transform: "translateX(0)" },
          to: { transform: "translateX(-50%)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.6s cubic-bezier(0.16,1,0.3,1) both",
        drift: "drift 26s ease-in-out infinite",
        marquee: "marquee 30s linear infinite",
      },
    },
  },
  plugins: [],
};

export default config;
