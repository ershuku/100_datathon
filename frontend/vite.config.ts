import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev: the backend runs on :8000 (uvicorn); same-origin in production (served by FastAPI).
const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/ui": backend, "/health": backend },
  },
  build: { outDir: "dist", sourcemap: false },
});
