import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { build, type Plugin, type ResolvedConfig } from 'vite'

/** Build a separate, lazy ESM graph even when the host build is a classic IIFE. */
export function mermaidRuntimePlugin(directory = 'mermaid'): Plugin {
  let config: ResolvedConfig
  return {
    name: 'self-hosted-mermaid-runtime',
    apply: 'build',
    configResolved(resolved) {
      config = resolved
    },
    async closeBundle() {
      await build({
        configFile: false,
        root: config.root,
        logLevel: config.logLevel,
        base: './',
        publicDir: false,
        build: {
          outDir: resolve(config.root, config.build.outDir, directory),
          emptyOutDir: true,
          target: config.build.target,
          rollupOptions: {
            // Unlike an app entry, this URL is imported for its default export.
            preserveEntrySignatures: 'strict',
            input: fileURLToPath(new URL('./mermaid-renderer.ts', import.meta.url)),
            output: {
              format: 'es',
              entryFileNames: 'renderer.js',
              chunkFileNames: 'chunks/[name]-[hash].js',
              assetFileNames: 'assets/[name]-[hash][extname]',
            },
          },
        },
      })
    },
  }
}
