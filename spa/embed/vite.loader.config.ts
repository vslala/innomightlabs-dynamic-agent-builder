/**
 * Builds embed.js, the small loader customers paste onto their sites. It is
 * written into the same dist folder as the app, so it must run second.
 */
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const embedDir = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  publicDir: false,
  define: {
    __EMBED_API_URL__: JSON.stringify(process.env.EMBED_API_URL || "https://api.innomightlabs.com"),
  },
  build: {
    outDir: `${embedDir}dist`,
    emptyOutDir: false,
    lib: {
      entry: `${embedDir}loader/index.ts`,
      name: "InnomightEmbedLoader",
      formats: ["iife"],
      fileName: () => "embed.js",
    },
  },
});
