/**
 * Builds the chat app the iframe loads: one classic script and one stylesheet
 * with fixed names, which the API's /embed/{public_key} shell references from
 * the CDN as embed/app.js and embed/app.css.
 */
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const embedDir = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  plugins: [react()],
  publicDir: false,
  build: {
    outDir: `${embedDir}dist`,
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      input: `${embedDir}app/main.tsx`,
      output: {
        format: "iife",
        inlineDynamicImports: true,
        entryFileNames: "embed/app.js",
        assetFileNames: (asset) =>
          asset.names.some((name) => name.endsWith(".css")) ? "embed/app.css" : "embed/assets/[name]-[hash][extname]",
      },
    },
  },
  preview: {
    port: 4174,
    strictPort: true,
  },
});
