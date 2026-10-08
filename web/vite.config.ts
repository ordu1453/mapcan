import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// The build goes right into the Python package: src/mapcan/web/static.
// In development (npm run dev) the API is proxied to `mapcan serve --no-browser`.
export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: "../src/mapcan/web/static",
    emptyOutDir: true,
    chunkSizeWarningLimit: 800,
  },
  server: {
    port: 5173,
    // The forms take field help from the format's schema (../schema/mapcan.schema.json)
    fs: { allow: [".."] },
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/ws": { target: "ws://127.0.0.1:8765", ws: true },
    },
  },
});
