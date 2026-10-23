import { useEffect } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { downloadsApiService } from "../services/downloads";
import { PluginDetailsPage } from "./PluginDetailsPage";

vi.mock("react", async (importOriginal) => ({
  ...await importOriginal<typeof import("react")>(),
  useEffect: vi.fn(),
}));
vi.mock("../components/Navbar", () => ({ Navbar: () => <nav /> }));
vi.mock("../components/Footer", () => ({ Footer: () => <footer /> }));
vi.mock("../components/ui/markdown-renderer", () => ({ MarkdownRenderer: () => null }));
vi.mock("../services/downloads", () => ({
  downloadsApiService: { getPlugin: vi.fn(() => new Promise(() => {})) },
}));

beforeEach(() => { vi.clearAllMocks(); });

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
