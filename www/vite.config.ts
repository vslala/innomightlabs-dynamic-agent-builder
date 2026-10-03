import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { site } from './src/content/site'

// The sitemap lists exactly the pages the SSG rendered, so it can never drift from the routes.
const renderedPaths: string[] = []

function sitemap(paths: string[]): string {
  const urls = paths
    .map((path) => new URL(path, site.url))
    .filter((url) => url.pathname !== '/404')
    .map((url) => `  <url><loc>${url.href}</loc></url>`)
    .sort()
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.join('\n')}\n</urlset>\n`
}

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  ssgOptions: {
    onPageRendered(route, html) {
      renderedPaths.push(route)
      return html
    },
    onFinished(dir) {
      writeFileSync(join(dir, 'sitemap.xml'), sitemap(renderedPaths))
    },
  },
})
