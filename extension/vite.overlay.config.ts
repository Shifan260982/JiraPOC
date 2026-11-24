import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The floating chat is a content script: Chrome loads it as a classic script, so it must be one
// self-contained IIFE with no imports. Built after the main build into the same dist folder.
export default defineConfig({
  plugins: [react()],
  define: { "process.env.NODE_ENV": JSON.stringify("production") },
  build: {
    outDir: "dist",
    emptyOutDir: false,
    lib: { entry: "src/overlay/main.tsx", name: "ForesightChat", formats: ["iife"], fileName: () => "overlay.js" },
  },
});
