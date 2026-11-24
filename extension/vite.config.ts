/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Two entries: the side panel page and the MV3 service worker. public/manifest.json is copied as-is.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "dist",
    // Not emptied: overlay.js comes from a separate build (vite.overlay.config.ts) and must survive this one.
    emptyOutDir: false,
    rollupOptions: {
      input: { sidepanel: "sidepanel.html", background: "src/background/index.ts" },
      output: { entryFileNames: "[name].js", chunkFileNames: "chunks/[name]-[hash].js" },
    },
  },
  test: { environment: "jsdom" },
});
