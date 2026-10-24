/**
 * Build-time output for public pages, generated from `src/routes/publicPages.ts`.
 *
 * - `sitemap.xml` and `robots.txt` at the site root.
 * - A copy of `index.html` at `<path>.html` for each indexable page,
 *   plus a noindex invitation shell that avoids the sensitive 404 redirect.
 *   GitHub Pages has no SPA fallback: an unknown path gets `404.html`, which
 *   answers with HTTP 404 and redirects in JavaScript. Crawlers stop at the 404,
 *   so each listed page needs a real file that answers 200 with the app shell.
 *   Pages serves `/docs/faq` from `docs/faq.html` directly; a `docs/faq/index.html`
 *   would first 301-redirect to `/docs/faq/`.
 *
 * The dev server serves the same `sitemap.xml` and `robots.txt` so they can be
 * checked locally; the page copies are only needed by the static host.
 */

import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import type { Plugin, ResolvedConfig } from "vite";

import { buildRobotsTxt, buildSitemap, indexablePaths, PUBLIC_PAGES } from "../src/routes/publicPages";

const wordpressMedia: Record<string, string> = {
  "screenshot-4.png": "image/png",
  "screenshot-5.png": "image/png",
  "screenshot-6.png": "image/png",
  "screenshot-7.png": "image/png",
  "screenshot-8.png": "image/png",
  "screenshot-9.png": "image/png",
  "demo.mp4": "video/mp4",
  "demo.vtt": "text/vtt; charset=utf-8",
  "demo-microservices.mp4": "video/mp4",
  "demo-microservices.vtt": "text/vtt; charset=utf-8",
};
const wordpressMediaPath = "plugins/wordpress-ai-search/";

export function publicPagesPlugin(): Plugin {
  let config: ResolvedConfig;
  const mediaSource = () => path.resolve(config.root, "../plugins/wordpress/innomight-ai-search/.wordpress-org");

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
        const url = (req.url ?? "").split("?")[0];
        const mediaPrefix = `${config.base}${wordpressMediaPath}`;
        if (url.startsWith(mediaPrefix)) {
          const filename = url.slice(mediaPrefix.length);
          // Exact allowlisting keeps encoded paths and traversal out of the filesystem.
          if (!Object.hasOwn(wordpressMedia, filename)) {
            res.statusCode = 404;
            res.end("Not found");
            return;
          }
          if (req.method !== "GET" && req.method !== "HEAD") {
            res.statusCode = 405;
            res.setHeader("Allow", "GET, HEAD");
            res.end();
            return;
          }
          void readFile(path.join(mediaSource(), filename)).then((body) => {
            res.setHeader("Content-Type", wordpressMedia[filename]);
            res.setHeader("Content-Length", body.length);
            res.end(req.method === "HEAD" ? undefined : body);
          }).catch(next);
          return;
        }
        const file = files[url];
        if (!file) return next();
        res.setHeader("Content-Type", `${file.type}; charset=utf-8`);
        res.end(file.body());
      });
    },
    async closeBundle() {
      // Vite also calls this when the dev server shuts down; only builds have output.
      if (config.command !== "build") return;
      const outDir = path.resolve(config.root, config.build.outDir);
      const mediaOutDir = path.join(outDir, wordpressMediaPath);
      await mkdir(mediaOutDir, { recursive: true });
      // Missing canonical media must fail the build rather than publish broken links.
      for (const filename of Object.keys(wordpressMedia)) {
        await copyFile(path.join(mediaSource(), filename), path.join(mediaOutDir, filename));
      }
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
      // The sensitive nonindexed route must not rely on the 404 query redirect.
      const invitationPage = PUBLIC_PAGES.find((page) => page.path === "/invitations/accept");
      if (invitationPage) {
        const file = path.join(outDir, `${invitationPage.path}.html`);
        await mkdir(path.dirname(file), { recursive: true });
        await writeFile(file, shell.replace(/<head>/i, '<head>\n    <meta name="robots" content="noindex, nofollow" />'));
      }
      config.logger.info(`public pages: sitemap with ${paths.length} URLs, ${paths.length - 1} indexed page shells${invitationPage ? ", 1 nonindexed invitation shell" : ""}`);
    },
  };
}
