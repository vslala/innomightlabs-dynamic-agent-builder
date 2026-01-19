import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  // With custom domain (innomightlabs.com), base should be '/'
  // Without custom domain, it would be '/innomightlabs-dynamic-agent-builder/'
  base: '/',
}))
