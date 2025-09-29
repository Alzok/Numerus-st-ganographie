import type { Config } from "tailwindcss";
import { fontFamily } from "tailwindcss/defaultTheme";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        border: "hsl(217.2 32.6% 17.5%)",
        input: "hsl(217.2 32.6% 17.5%)",
        ring: "hsl(210 22% 13%)",
        background: "hsl(222.2 47.4% 11.2%)",
        foreground: "hsl(210 40% 98%)",
        primary: {
          DEFAULT: "hsl(210 40% 98%)",
          foreground: "hsl(222.2 47.4% 11.2%)",
        },
        secondary: {
          DEFAULT: "hsla(217 33% 18% / 0.7)",
          foreground: "hsl(210 40% 98%)",
        },
        muted: {
          DEFAULT: "hsla(217 19% 27% / 0.5)",
          foreground: "hsl(215.4 16.3% 56.9%)",
        },
        accent: {
          DEFAULT: "hsla(187 100% 42% / 0.85)",
          foreground: "hsl(222.2 47.4% 11.2%)",
        },
        destructive: {
          DEFAULT: "hsl(0 84.2% 60.2%)",
          foreground: "hsl(210 40% 98%)",
        },
      },
      borderRadius: {
        lg: "1rem",
        md: "0.75rem",
        sm: "0.5rem",
      },
      fontFamily: {
        sans: ["Inter", ...fontFamily.sans],
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
