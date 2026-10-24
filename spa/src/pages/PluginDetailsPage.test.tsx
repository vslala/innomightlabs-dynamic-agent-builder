import { useEffect, useState } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { downloadsApiService } from "../services/downloads";
import { PluginDetailsPage } from "./PluginDetailsPage";

vi.mock("react", async (importOriginal) => ({
  ...await importOriginal<typeof import("react")>(),
  useEffect: vi.fn(),
  useState: vi.fn((await importOriginal<typeof import("react")>()).useState),
}));
vi.mock("../components/Navbar", () => ({ Navbar: () => <nav /> }));
vi.mock("../components/Footer", () => ({ Footer: () => <footer /> }));
vi.mock("../components/ui/markdown-renderer", () => ({ MarkdownRenderer: () => null }));
vi.mock("../services/downloads", () => ({
  downloadsApiService: { getPlugin: vi.fn(() => new Promise(() => {})) },
}));

beforeEach(() => { vi.clearAllMocks(); vi.unstubAllEnvs(); });

describe("plugin demo presentation", () => {
  function renderPlugin(id: string, base = "/") {
    vi.stubEnv("BASE_URL", base);
    vi.mocked(useState)
      .mockReturnValueOnce([{
        id, name: "Test plugin", kind: "Plugin", tagline: "Search your site",
        description: "Test description", version: "1.0", platform: "WordPress",
        download_url: "/download.zip", readme_markdown: "README",
      }, vi.fn()])
      .mockReturnValueOnce(["success", vi.fn()]);
    return renderToStaticMarkup(
      <MemoryRouter initialEntries={[`/downloads/plugins/${id}`]}>
        <PluginDetailsPage />
      </MemoryRouter>,
    );
  }

  it.each(["/", "/preview/"])("renders an accessible, opt-in video with base %s", (base) => {
    const html = renderPlugin("wordpress-ai-search", base);
    expect(html).toContain("See WordPress AI Search in action");
    expect(html).toContain('aria-labelledby="wordpress-search-demo-title"');
    expect(html.match(/<video/g)).toHaveLength(2);
    expect(html).toMatch(/<video[^>]* controls=""[^>]* playsInline=""[^>]* preload="none"/);
    for (const [file, poster] of [["demo", "screenshot-4.png"], ["demo-microservices", "screenshot-7.png"]]) {
      expect(html).toContain(`aria-labelledby="${file}-title"`);
      expect(html).toContain(`aria-describedby="${file}-description"`);
      expect(html).toContain(`poster="${base}plugins/wordpress-ai-search/${poster}"`);
      expect(html).toContain(`<source src="${base}plugins/wordpress-ai-search/${file}.mp4" type="video/mp4"`);
      expect(html).toContain(`<track kind="captions" src="${base}plugins/wordpress-ai-search/${file}.vtt" srcLang="en" label="English" default=""`);
    }
    expect(html.toLowerCase()).not.toContain("autoplay");
  });

  it.each(["wordpress", "vscode", "macos"])("does not show demo media for %s", (id) => {
    const html = renderPlugin(id);
    expect(html).not.toContain("<video");
    expect(html).not.toContain("plugins/wordpress-ai-search/");
    expect(html).not.toContain("See WordPress AI Search in action");
  });
});

describe("plugin detail route loading", () => {
  it.each([
    ["/downloads/plugins/wordpress-ai-search", "wordpress-ai-search", ""],
    ["/downloads/plugins/:pluginId", "wordpress-ai-search", ""],
    ["/downloads/plugins/:pluginId", "wordpress", ""],
    ["/downloads/plugins/:pluginId", "vscode", ""],
    ["/downloads/plugins/wordpress-ai-search", "wordpress-ai-search", "/preview"],
  ])("loads the matching plugin on %s (%s, basename %s)", (route, pluginId, basename) => {
    const html = renderToStaticMarkup(
      <MemoryRouter basename={basename || undefined} initialEntries={[`${basename}/downloads/plugins/${pluginId}`]}>
        <Routes><Route path={route} element={<PluginDetailsPage />} /></Routes>
      </MemoryRouter>,
    );
    expect(html).toContain("Loading plugin details...");
    expect(html).toContain(`href="${basename}/downloads"`);

    // SSR records effects without a DOM; run only the page's load effect to
    // verify its API selection. The pending mock avoids state-render concerns.
    const load = vi.mocked(useEffect).mock.calls.find(([, deps]) => deps?.[0] === pluginId)?.[0];
    expect(load).toBeDefined();
    const cleanup = load?.();
    expect(downloadsApiService.getPlugin).toHaveBeenCalledExactlyOnceWith(pluginId);
    if (typeof cleanup === "function") cleanup();
  });
});
