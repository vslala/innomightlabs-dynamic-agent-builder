/**
 * Build-time output for public pages, generated from `src/routes/publicPages.ts`.
 *
 * - `sitemap.xml` and `robots.txt` at the site root.
 * - A copy of `index.html` at `<path>.html` for each indexable page.
 *   GitHub Pages has no SPA fallback: an unknown path gets `404.html`, which
 *   answers with HTTP 404 and redirects in JavaScript. Crawlers stop at the 404,
 *   so each listed page needs a real file that answers 200 with the app shell.
 *   Pages serves `/docs/faq` from `docs/faq.html` directly; a `docs/faq/index.html`
 *   would first 301-redirect to `/docs/faq/`.
 *
 * The dev server serves the same `sitemap.xml` and `robots.txt` so they can be
 * checked locally; the page copies are only needed by the static host.
 */

import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import type { Plugin, ResolvedConfig } from "vite";

import { buildRobotsTxt, buildSitemap, indexablePaths } from "../src/routes/publicPages";

export function publicPagesPlugin(): Plugin {
  let config: ResolvedConfig;

  return {
    name: "innomight-public-pages",
    configResolved(resolved) {
      config = resolved;
    },
    configureServer(server) {
      const files: Record<string, { type: string; body: () => string }> = {
        "/sitemap.xml": { type: "application/xml", body: () => buildSitemap(indexablePaths()) },
        "/robots.txt": { type: "text/plain", body: () => buildRobotsTxt() },
      };
      server.middlewares.use((req, res, next) => {
        const file = files[(req.url ?? "").split("?")[0]];
        if (!file) return next();
        res.setHeader("Content-Type", `${file.type}; charset=utf-8`);
        res.end(file.body());
      });
    },
    async closeBundle() {
      // Vite also calls this when the dev server shuts down; only builds have output.
      if (config.command !== "build") return;
      const outDir = path.resolve(config.root, config.build.outDir);
      const paths = indexablePaths();
      const shell = await readFile(path.join(outDir, "index.html"), "utf8");

      await writeFile(path.join(outDir, "sitemap.xml"), buildSitemap(paths));
      await writeFile(path.join(outDir, "robots.txt"), buildRobotsTxt());
      for (const page of paths) {
        if (page === "/") continue;
        const file = path.join(outDir, `${page}.html`);
        await mkdir(path.dirname(file), { recursive: true });
        await writeFile(file, shell);
      }
      config.logger.info(`public pages: sitemap with ${paths.length} URLs, ${paths.length - 1} page shells`);
    },
  };
}
