import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const devHost = process.env.VITE_DEV_HOST || "127.0.0.1";
const devPort = Number(process.env.VITE_PORT || "5173");
const apiTarget = process.env.VITE_API_TARGET || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    // Windows: default "localhost" can bind IPv6-only (::1), so http://127.0.0.1:port fails.
    host: devHost,
    port: devPort,
    strictPort: true,
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    globals: true,
  },
});
