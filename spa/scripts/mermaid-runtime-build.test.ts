import { mkdtemp, readFile, readdir, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { build } from 'vite'
import { describe, expect, it } from 'vitest'
import { mermaidRuntimePlugin } from './vite-plugin-mermaid-runtime'

const entry = fileURLToPath(new URL('../src/components/ui/mermaid-runtime.ts', import.meta.url))

describe('Mermaid lazy host build', () => {
  it('emits a default-exported ESM renderer and its self-hosted chunks', async () => {
    const outDir = await mkdtemp(join(tmpdir(), 'mermaid-build-test-'))
    try {
      await build({
        configFile: false,
        publicDir: false,
        logLevel: 'silent',
        plugins: [mermaidRuntimePlugin('embed/mermaid')],
        build: {
          outDir,
          lib: { entry, formats: ['iife'], name: 'MermaidRuntimeTest' },
        },
      })
      const renderer = await readFile(join(outDir, 'embed/mermaid/renderer.js'), 'utf8')
      // Vite's normal app-entry semantics silently discard this export without
      // preserveEntrySignatures: strict, breaking the browser's dynamic import.
      expect(renderer).toMatch(/export\s*\{[^}]*\bdefault\b/)
      expect(renderer).toContain('./chunks/')
      expect(renderer).not.toMatch(/from\s*["']mermaid["']/)
      expect((await readdir(join(outDir, 'embed/mermaid/chunks'))).length).toBeGreaterThan(10)
    } finally {
      await rm(outDir, { recursive: true, force: true })
    }
  }, 30_000)
  it.each(['es', 'iife'] as const)('keeps Mermaid outside the %s application graph', async (format) => {
    const result = await build({
      configFile: false,
      publicDir: false,
      logLevel: 'silent',
      define: {
        'import.meta.env.DEV': 'false',
        'import.meta.env.MERMAID_EMBED': JSON.stringify(format === 'iife' ? 'true' : ''),
      },
      build: {
        write: false,
        minify: false,
        lib: { entry, formats: [format], name: 'MermaidRuntimeTest' },
        rollupOptions: { output: { inlineDynamicImports: format === 'iife' } },
      },
    })
    const builds = Array.isArray(result) ? result : [result]
    for (const built of builds) {
      if (!('output' in built)) throw new Error('Expected a completed build')
      const chunks = built.output.filter((output) => output.type === 'chunk')
      expect(chunks).toHaveLength(1)
      const [chunk] = chunks
      expect(Object.keys(chunk.modules).sort()).toEqual([
        entry,
        entry.replace('mermaid-runtime.ts', 'mermaid-runtime.module.css'),
      ].sort())
      expect(chunk.code).toContain('mermaid/renderer.js')
      expect(chunk.code).toMatch(/import\(\s*\/\* @vite-ignore \*\/\s*url\s*\)/)
      expect(chunk.code).not.toContain('mermaid-renderer.ts')
      expect(chunk.code).not.toContain('DOMPurify')
      expect(chunk.code.length).toBeLessThan(6_000)
      if (format === 'iife') {
        expect(chunk.code).toContain('document.currentScript')
        expect(chunk.code).toContain('Cannot locate the widget Mermaid runtime')
      }
    }
  })
})
