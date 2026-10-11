import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it, vi } from "vitest";
import type { ResolvedConfig } from "vite";
import { publicPagesPlugin } from "./vite-plugin-public-pages";
import { indexablePaths } from "../src/routes/publicPages";

const shell = '<!doctype html><html><head><title>App</title></head><body><div id="root"></div></body></html>';

describe("static public route shells", () => {
  it("emits only the additional nonindexed invitation shell, leaving public SEO unchanged", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "invitation-shell-test-"));
    try {
      await mkdir(path.join(root, "dist"));
      await writeFile(path.join(root, "dist/index.html"), shell);
      const plugin = publicPagesPlugin();
      const configResolved = plugin.configResolved;
      const closeBundle = plugin.closeBundle;
      if (typeof configResolved !== "function" || typeof closeBundle !== "function") throw new Error("Expected callable plugin hooks");
      const config = { root, command: "build", build: { outDir: "dist" }, logger: { info: vi.fn() } } as unknown as ResolvedConfig;
      configResolved.call({} as never, config);
      await closeBundle.call({} as never);
      const invitation = await readFile(path.join(root, "dist/invitations/accept.html"), "utf8");
      expect(invitation).toContain('<meta name="robots" content="noindex, nofollow" />');
      expect(invitation).toContain('<div id="root"></div>');
      expect(await readFile(path.join(root, "dist/docs/faq.html"), "utf8")).toBe(shell);
      const sitemap = await readFile(path.join(root, "dist/sitemap.xml"), "utf8");
      expect(sitemap).not.toContain("/invitations/accept");
      expect(sitemap.match(/<url>/g)).toHaveLength(indexablePaths().length);
      await expect(readFile(path.join(root, "dist/login.html"), "utf8")).rejects.toMatchObject({ code: "ENOENT" });
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
});
