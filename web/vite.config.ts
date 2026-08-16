import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev mode: Vite serves the UI on :5173 and proxies /api to the FastAPI
// backend on :8000, so the browser only ever talks to one origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
