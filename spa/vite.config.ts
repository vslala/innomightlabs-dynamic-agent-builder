/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { publicPagesPlugin } from './scripts/vite-plugin-public-pages'
import { mermaidRuntimePlugin } from './scripts/vite-plugin-mermaid-runtime'
import { nativeHtmlPlugin } from './scripts/vite-plugin-native-html'

export default defineConfig(({ mode }) => {
  // The store apps' build (`yarn build:native`): no crawler files, no analytics, its own output folder.
  const native = mode === 'native'
  if (native) {
    // A VITE_API_BASE_URL exported for web development must not leak into a store build: the app's API comes
    // from .env.native unless NATIVE_API_BASE_URL says otherwise (a simulator against a local API).
    delete process.env.VITE_API_BASE_URL
    if (process.env.NATIVE_API_BASE_URL) process.env.VITE_API_BASE_URL = process.env.NATIVE_API_BASE_URL
  }
  return {
    plugins: [react(), tailwindcss(), native ? nativeHtmlPlugin() : publicPagesPlugin(), mermaidRuntimePlugin()],
    // With custom domain (innomightlabs.com), base is '/'
    base: '/',
    build: { outDir: native ? 'dist-native' : 'dist' },
    // Tests run against the web adapter unless they install a fake (src/platform/testing.ts).
    test: { setupFiles: ['./src/platform/testSetup.ts'] },
  }
})
