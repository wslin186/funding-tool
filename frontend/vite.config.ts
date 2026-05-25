import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/funding/",
  plugins: [react()],
  build: {
    outDir: "dist",
    sourcemap: false,
    rollupOptions: { output: { manualChunks: { recharts: ["recharts"] } } },
  },
  test: { environment: "jsdom", globals: true, setupFiles: "./src/test-setup.ts" },
});
