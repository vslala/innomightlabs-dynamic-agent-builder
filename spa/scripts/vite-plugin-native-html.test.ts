import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { nativeHtml } from "./vite-plugin-native-html";

const indexHtml = readFileSync(new URL("../index.html", import.meta.url), "utf8");

describe("the store apps' index.html", () => {
  const html = nativeHtml(indexHtml);

  it("carries no analytics or ad tags", () => {
    expect(indexHtml).toContain("googletagmanager");
    for (const tag of ["googletagmanager", "GTM-", "G-LZ38HL06XF", "AW-", "analytics:"]) expect(html).not.toContain(tag);
  });

  it("draws under the notch, once", () => {
    expect(html).toMatch(/<meta name="viewport" content="[^"]*viewport-fit=cover"/);
    expect(nativeHtml(html).match(/viewport-fit=cover/g)).toHaveLength(1);
  });

  it("keeps the app itself", () => {
    expect(html).toContain('<div id="root"></div>');
    expect(html).toContain('src="/src/main.tsx"');
  });
});
