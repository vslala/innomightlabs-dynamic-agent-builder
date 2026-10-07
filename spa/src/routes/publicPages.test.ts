import { describe, expect, it } from "vitest";

import { buildRobotsTxt, buildSitemap, indexablePages, indexablePaths, PUBLIC_PAGES } from "./publicPages";

describe("public pages", () => {
  it("lists only indexable pages with a fixed path", () => {
    const paths = indexablePaths([
      { path: "/", indexed: true },
      { path: "/login", indexed: false },
      { path: "/downloads/plugins/:pluginId", indexed: true },
      { path: "/docs/faq", indexed: true },
    ]);

    expect(paths).toEqual(["/", "/docs/faq"]);
  });

  it("keeps the dashboard and sign-in flow out of the sitemap", () => {
    const paths = indexablePaths();

    expect(paths).toContain("/whats-new");
    expect(paths).not.toContain("/login");
    expect(paths.some((path) => path.startsWith("/dashboard"))).toBe(false);
  });

  it("gives every listed page a title and section for /sitemap", () => {
    for (const page of indexablePages()) {
      expect(page.title, page.path).toBeTruthy();
      expect(page.section, page.path).toBeTruthy();
    }
  });

  it("has no duplicate paths", () => {
    const paths = PUBLIC_PAGES.map((page) => page.path);
    expect(new Set(paths).size).toBe(paths.length);
  });

  it("writes absolute, escaped URLs", () => {
    const xml = buildSitemap(["/", "/docs/a&b"], "https://example.com");

    expect(xml).toContain("<loc>https://example.com/</loc>");
    expect(xml).toContain("<loc>https://example.com/docs/a&amp;b</loc>");
    expect(xml.startsWith('<?xml version="1.0" encoding="UTF-8"?>')).toBe(true);
    expect(xml).not.toContain("xml-stylesheet");
  });

  it("points robots.txt at the sitemap", () => {
    expect(buildRobotsTxt("https://example.com")).toContain("Sitemap: https://example.com/sitemap.xml");
  });
});
