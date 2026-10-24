import { mkdtemp, mkdir, readFile, readdir, rm, unlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it, vi } from "vitest";
import type { Connect, ResolvedConfig } from "vite";
import { publicPagesPlugin } from "./vite-plugin-public-pages";
import { indexablePaths } from "../src/routes/publicPages";

const mediaFiles = [
  "screenshot-4.png", "screenshot-5.png", "screenshot-6.png", "screenshot-7.png", "screenshot-8.png", "screenshot-9.png",
  "demo.mp4", "demo.vtt", "demo-microservices.mp4", "demo-microservices.vtt",
];

async function createFixture() {
  const directory = await mkdtemp(path.join(tmpdir(), "public-pages-test-"));
  const root = path.join(directory, "spa");
  const media = path.join(directory, "plugins/wordpress/innomight-ai-search/.wordpress-org");
  await mkdir(path.join(root, "dist"), { recursive: true });
  await mkdir(media, { recursive: true });
  for (const filename of [...mediaFiles, "private.txt"]) {
    await writeFile(path.join(media, filename), `canonical ${filename}`);
  }
  return { directory, root, media };
}

function setupPlugin(root: string, command = "build", base = "/") {
  const plugin = publicPagesPlugin();
  const configResolved = plugin.configResolved;
  if (typeof configResolved !== "function") throw new Error("Expected callable config hook");
  configResolved.call({} as never, {
    root, command, base, build: { outDir: "dist" }, logger: { info: vi.fn() },
  } as unknown as ResolvedConfig);
  return plugin;
}

const shell = '<!doctype html><html><head><title>App</title></head><body><div id="root"></div></body></html>';

describe("WordPress demo media", () => {
  it.each(mediaFiles)("fails a build when canonical %s is missing", async (filename) => {
    const { root, directory, media } = await createFixture();
    try {
      await unlink(path.join(media, filename));
      const closeBundle = setupPlugin(root).closeBundle;
      if (typeof closeBundle !== "function") throw new Error("Expected callable build hook");
      await expect(closeBundle.call({} as never)).rejects.toMatchObject({ code: "ENOENT", path: path.join(media, filename) });
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });

  it.each(["/", "/preview/"])("serves only allowlisted media in development with base %s", async (base) => {
    const { root, directory } = await createFixture();
    try {
      let middleware: Connect.NextHandleFunction | undefined;
      const configureServer = setupPlugin(root, "serve", base).configureServer;
      if (typeof configureServer !== "function") throw new Error("Expected callable server hook");
      configureServer.call({} as never, {
        middlewares: { use: (handler: Connect.NextHandleFunction) => { middleware = handler; } },
      } as never);
      const request = (filename: string, method = "GET") => new Promise<{ status: number; headers: Record<string, unknown>; body: unknown }>((resolve, reject) => {
        const headers: Record<string, unknown> = {};
        const response = {
          statusCode: 200,
          setHeader: (name: string, value: unknown) => { headers[name] = value; },
          end: (body: unknown) => resolve({ status: response.statusCode, headers, body }),
        };
        middleware?.({ url: `${base}plugins/wordpress-ai-search/${filename}`, method } as never, response as never, (error?: unknown) => reject(error ?? new Error("Unexpected fallthrough")));
      });
      for (const filename of mediaFiles) {
        const result = await request(`${filename}?v=1`);
        expect(result.status).toBe(200);
        expect(result.headers["Content-Type"]).toBe(filename.endsWith(".png") ? "image/png" : filename.endsWith(".mp4") ? "video/mp4" : "text/vtt; charset=utf-8");
        expect(result.body).toEqual(Buffer.from(`canonical ${filename}`));
      }
      const head = await request("demo.mp4", "HEAD");
      expect(head.body).toBeUndefined();
      expect(head.headers["Content-Length"]).toBeGreaterThan(0);
      expect((await request("demo.mp4", "POST")).status).toBe(405);
      for (const filename of ["private.txt", "../private.txt", "%2e%2e/private.txt", "screenshot-4.png/../private.txt", "toString"]) {
        expect((await request(filename)).status).toBe(404);
      }
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });
});

describe("static public route shells", () => {
  it("emits only the additional nonindexed invitation shell, leaving public SEO unchanged", async () => {
    const { root, directory } = await createFixture();
    try {
      await writeFile(path.join(root, "dist/index.html"), shell);
      const closeBundle = setupPlugin(root).closeBundle;
      if (typeof closeBundle !== "function") throw new Error("Expected callable build hook");
      await closeBundle.call({} as never);
      const invitation = await readFile(path.join(root, "dist/invitations/accept.html"), "utf8");
      expect(invitation).toContain('<meta name="robots" content="noindex, nofollow" />');
      expect(invitation).toContain('<div id="root"></div>');
      expect(await readFile(path.join(root, "dist/docs/faq.html"), "utf8")).toBe(shell);
      const sitemap = await readFile(path.join(root, "dist/sitemap.xml"), "utf8");
      expect(sitemap).not.toContain("/invitations/accept");
      expect(sitemap.match(/<url>/g)).toHaveLength(indexablePaths().length);
      await expect(readFile(path.join(root, "dist/login.html"), "utf8")).rejects.toMatchObject({ code: "ENOENT" });
      const output = path.join(root, "dist/plugins/wordpress-ai-search");
      expect((await readdir(output)).sort()).toEqual([...mediaFiles].sort());
      for (const filename of mediaFiles) {
        expect(await readFile(path.join(output, filename))).toEqual(await readFile(path.join(directory, "plugins/wordpress/innomight-ai-search/.wordpress-org", filename)));
      }
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });
});
