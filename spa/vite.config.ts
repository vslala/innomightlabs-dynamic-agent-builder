import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { publicPagesPlugin } from './scripts/vite-plugin-public-pages'
import { mermaidRuntimePlugin } from './scripts/vite-plugin-mermaid-runtime'

export default defineConfig({
  plugins: [react(), tailwindcss(), publicPagesPlugin(), mermaidRuntimePlugin()],
  // With custom domain (innomightlabs.com), base is '/'
  base: '/',
})
