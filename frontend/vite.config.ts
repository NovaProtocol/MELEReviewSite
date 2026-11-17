import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/* The build lands inside the Python package, because the image ships one tree.
   Manifest mode lets the shell template find the hashed file names. */
export default defineConfig({
  plugins: [react()],
  base: "/static/app/",
  build: {
    outDir: "../app/static/app",
    emptyOutDir: true,
    manifest: true,
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ["react", "react-dom"],
          dock: ["dockview"],
          math: ["mathjs"],
        },
      },
    },
  },
});
