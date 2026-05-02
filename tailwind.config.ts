import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/app/**/*.{ts,tsx}",
    "./src/components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Ara projesi ile uyumlu — admin header gradient'ı baz alındı.
        brand: {
          start: "#667eea",
          end: "#764ba2",
        },
        ink: {
          900: "#1e3a5f",
          700: "#374151",
          500: "#666666",
        },
      },
      fontFamily: {
        sans: ["system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
      },
      boxShadow: {
        brand: "0 4px 15px rgba(102, 126, 234, 0.3)",
      },
      borderRadius: {
        card: "12px",
      },
    },
  },
  plugins: [],
};

export default config;
