/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: "#1B3A5C",
        accent: "#2dd4bf",
        surface: {
          DEFAULT: "rgba(255,255,255,0.04)",
          raised: "rgba(255,255,255,0.07)",
        },
      },
      fontFamily: {
        sans: ['"DM Sans"', "system-ui", "sans-serif"],
        display: ['"Outfit"', "system-ui", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 60px -12px rgba(45, 212, 191, 0.35)",
        "glow-sm": "0 0 40px -10px rgba(45, 212, 191, 0.25)",
        panel: "0 25px 50px -12px rgba(0, 0, 0, 0.5)",
      },
      backgroundImage: {
        "grid-fine":
          "linear-gradient(rgba(148,163,184,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,0.06) 1px, transparent 1px)",
      },
    },
  },
  plugins: [],
};
