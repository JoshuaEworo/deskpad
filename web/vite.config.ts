import { defineConfig } from "vite";

export default defineConfig({
  build: { outDir: "../host/deskpad/static", emptyOutDir: true },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/ws": { target: "ws://127.0.0.1:8765", ws: true },
    },
  },
});
