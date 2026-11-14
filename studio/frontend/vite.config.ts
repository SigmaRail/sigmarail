import { defineConfig } from "vitest/config";
import { loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "SIGMARAIL_");
  const apiTarget = env.SIGMARAIL_API_TARGET ?? "http://127.0.0.1:8001";
  const apiProxy = {
    "/api": { target: apiTarget, changeOrigin: true },
    "/health": { target: apiTarget, changeOrigin: true },
  };

  return {
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    allowedHosts: ["turnip.tail850cb1.ts.net"],
    proxy: apiProxy,
  },
  preview: {
    port: 4173,
    proxy: apiProxy,
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
  };
});
