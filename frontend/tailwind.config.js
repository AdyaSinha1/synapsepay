/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        plum: {
          50: "#F5F2FB",
          100: "#EDE9F7",
          700: "#423859",
          800: "#332B4A",
          900: "#262038",
          950: "#1C1730",
        },
        volt: {
          DEFAULT: "#D9F45B",
          deep: "#B8D62E",
          shadow: "#A9C32E",
          ink: "#33400A",
          soft: "#F2F8D9",
        },
        lilac: {
          DEFAULT: "#8B7BE8",
          bright: "#A99AF0",
          200: "#DCD5F8",
          100: "#EFEBFC",
          ink: "#4A3D96",
        },
        coral: {
          DEFAULT: "#E96D62",
          100: "#FBE7E4",
          ink: "#9A3B31",
        },
        sun: {
          DEFAULT: "#E9B44C",
          100: "#FAF0DB",
          ink: "#7A5416",
        },
        ivory: "#F7F4EB",
        ink: "#262038",
        mute: "#6B6580",
        line: "#ECE7DB",
      },
      fontFamily: {
        sans: ['"DM Sans"', "ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"],
        display: ['"Sora"', '"DM Sans"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "Consolas", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(38,32,56,0.05), 0 10px 28px -14px rgba(38,32,56,0.12)",
        volt: "0 3px 0 0 #A9C32E",
        plum: "0 3px 0 0 #171226",
      },
    },
  },
  plugins: [],
};
