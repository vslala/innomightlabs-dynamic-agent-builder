import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { publicPagesPlugin } from './scripts/vite-plugin-public-pages'

export default defineConfig({
  plugins: [react(), tailwindcss(), publicPagesPlugin()],
  // With custom domain (innomightlabs.com), base is '/'
  base: '/',
})
