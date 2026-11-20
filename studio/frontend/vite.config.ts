import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import tsconfigPaths from "vite-tsconfig-paths";

const workspaceRoot = fileURLToPath(new URL("../..", import.meta.url));

const apiProxy = {
  "/api": {
    target: "http://127.0.0.1:5001",
    changeOrigin: true,
  },
  "/lbcheck": {
    target: "http://127.0.0.1:5001",
    changeOrigin: true,
  },
};

export default defineConfig({
  plugins: [react(), tsconfigPaths({ projects: ["./tsconfig.app.json"], loose: true })],
  resolve: {
    // AppTension's shared components import their own package through this alias.
    // The TS paths plugin intentionally limits itself to frontend/src, so keep the
    // same core alias available while bundling those shared component sources.
    alias: [
      {
        find: /^@sb\/webapp-core\/(.*)$/,
        replacement: `${workspaceRoot}/packages/webapp-libs/webapp-core/src/$1`,
      },
    ],
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
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
});
