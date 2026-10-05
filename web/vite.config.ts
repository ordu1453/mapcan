import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// Сборка кладётся прямо в Python-пакет: src/canmap/web/static.
// В режиме разработки (npm run dev) API проксируется на `canmap serve --no-browser`.
export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: "../src/canmap/web/static",
    emptyOutDir: true,
    chunkSizeWarningLimit: 800,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/ws": { target: "ws://127.0.0.1:8765", ws: true },
    },
  },
});
