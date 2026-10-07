/**
 * Every route a signed-out visitor can open.
 *
 * This list is the single source for three things: the public `<Route>`s in
 * App.tsx, `sitemap.xml`, and the per-page copies of `index.html` the build
 * writes so GitHub Pages answers those URLs with 200 instead of its 404 redirect.
 * App.tsx maps each path to its page with a `Record<PublicPath, ...>`, so a page
 * cannot be routed without being listed here, or listed without being routed.
 *
 * Set `indexed: false` for pages search engines should skip (sign-in, payment
 * returns). Paths with a `:param` are routed but never listed in the sitemap.
 * Indexed pages carry a `title` and `section`, which the /sitemap page lists.
 */

export type SitemapSection = "Product" | "Documentation" | "Legal";

export interface PublicPage {
  path: string;
  indexed: boolean;
  title?: string;
  section?: SitemapSection;
}

export const SITE_ORIGIN = "https://innomightlabs.com";

export const PUBLIC_PAGES = [
  { path: "/", indexed: true, title: "Home", section: "Product" },
  { path: "/pricing", indexed: true, title: "Pricing", section: "Product" },
  { path: "/downloads", indexed: true, title: "Downloads", section: "Product" },
  { path: "/downloads/plugins/:pluginId", indexed: false },
  { path: "/whats-new", indexed: true, title: "What's New", section: "Product" },
  { path: "/contact", indexed: true, title: "Contact", section: "Product" },
  { path: "/docs/quick-start", indexed: true, title: "Quick Start", section: "Documentation" },
  { path: "/docs/automations", indexed: true, title: "Automations", section: "Documentation" },
  { path: "/docs/agent-to-agent", indexed: true, title: "Agent2Agent", section: "Documentation" },
  { path: "/docs/public-api", indexed: true, title: "Public API", section: "Documentation" },
  { path: "/docs/faq", indexed: true, title: "FAQ", section: "Documentation" },
  { path: "/legal/terms", indexed: true, title: "Terms of Service", section: "Legal" },
  { path: "/legal/privacy", indexed: true, title: "Privacy Policy", section: "Legal" },
  { path: "/legal/pricing", indexed: true, title: "Pricing Policy", section: "Legal" },
  { path: "/sitemap", indexed: true, title: "Sitemap", section: "Product" },
  { path: "/login", indexed: false },
  { path: "/login-success", indexed: false },
  { path: "/payments/success", indexed: false },
  { path: "/payments/cancel", indexed: false },
] as const satisfies readonly PublicPage[];

export type PublicPath = (typeof PUBLIC_PAGES)[number]["path"];

/** The pages that belong in the sitemap: indexable and with a fixed path. */
export function indexablePages(pages: readonly PublicPage[] = PUBLIC_PAGES): PublicPage[] {
  return pages.filter((page) => page.indexed && !page.path.includes(":"));
}

export function indexablePaths(pages: readonly PublicPage[] = PUBLIC_PAGES): string[] {
  return indexablePages(pages).map((page) => page.path);
}

export function buildSitemap(paths: string[], origin: string = SITE_ORIGIN): string {
  const urls = paths.map((path) => `  <url>\n    <loc>${escapeXml(origin + path)}</loc>\n  </url>`);
  return [
    // No XSL stylesheet: browsers are removing XSLT. People read /sitemap instead.
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ...urls,
    "</urlset>",
    "",
  ].join("\n");
}

export function buildRobotsTxt(origin: string = SITE_ORIGIN): string {
  return [
    "User-agent: *",
    "Disallow: /dashboard",
    "Disallow: /login-success",
    "Disallow: /payments/",
    "",
    `Sitemap: ${origin}/sitemap.xml`,
    "",
  ].join("\n");
}

function escapeXml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}
