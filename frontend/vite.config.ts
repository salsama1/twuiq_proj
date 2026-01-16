import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000";

  return {
    plugins: [react()],
    server: {
      proxy: {
        // Use simple prefix matching (more reliable than regex-like strings).
        "/agent": { target, changeOrigin: true },
        "/query": { target, changeOrigin: true },
        "/occurrences": { target, changeOrigin: true },
        "/advanced": { target, changeOrigin: true },
        "/files": { target, changeOrigin: true },
        "/rasters": { target, changeOrigin: true },
        "/jobs": { target, changeOrigin: true },
        "/speech": { target, changeOrigin: true },
      },
    },
  };
});
