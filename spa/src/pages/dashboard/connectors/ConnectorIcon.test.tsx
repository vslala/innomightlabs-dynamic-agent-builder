import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ConnectorIcon } from "./ConnectorIcon";
import styles from "./ConnectorCatalog.module.css";

const providersDirectory = new URL("../../../../../api/src/connectors/mcp/providers/", import.meta.url);
const accountDefinitions = new URL("../../../../../api/src/connectors/service.py", import.meta.url);
const providerIcons = readdirSync(providersDirectory)
  .filter((file) => file.endsWith(".py"))
  .flatMap((file) => [...readFileSync(new URL(file, providersDirectory), "utf8").matchAll(/icon="([^"]+)"/g)])
  .map((match) => match[1]);
const accountIcons = [...readFileSync(accountDefinitions, "utf8").matchAll(/icon="([^"]+)"/g)]
  .map((match) => match[1]);
const socialDirectory = new URL("../../../../../api/src/connectors/social/networks/", import.meta.url);
const socialIcons = readdirSync(socialDirectory)
  .filter((file) => file.endsWith(".py"))
  .flatMap((file) => [...readFileSync(new URL(file, socialDirectory), "utf8").matchAll(/^\s+icon = "([^"]+)"/gm)])
  .map((match) => match[1]);

function render(icon: string, name = "Provider", size?: "md" | "sm") {
  return renderToStaticMarkup(<ConnectorIcon icon={icon} name={name} size={size} />);
}

describe("connector brand icons", () => {
  it("finds the configured MCP providers and Google accounts", () => {
    expect(providerIcons.length).toBeGreaterThan(0);
    expect(accountIcons.length).toBeGreaterThan(0);
    expect(socialIcons.length).toBeGreaterThan(0);
  });

  it.each([...new Set([...providerIcons, ...accountIcons, ...socialIcons])])("renders a local brand asset for %s", (icon) => {
    const html = render(icon);
    const src = html.match(/<img[^>]+src="([^"]+)"/)?.[1];
    expect(src).toBeDefined();
    expect(src).not.toMatch(/^https?:/);
    expect(html).toContain('alt=""');
    expect(html).toContain('aria-hidden="true"');
  });

  it("has valid PNG or SVG files rather than downloaded error pages", () => {
    const directory = new URL("../../../assets/connectors/", import.meta.url);
    for (const file of readdirSync(directory)) {
      if (!/\.(png|svg)$/.test(file)) continue;
      const bytes = readFileSync(fileURLToPath(new URL(file, directory)));
      if (file.endsWith("png")) {
        expect(bytes.subarray(0, 8).toString("hex")).toBe("89504e470d0a1a0a");
        expect(bytes.readUInt32BE(16)).toBeGreaterThanOrEqual(64);
        expect(bytes.readUInt32BE(20)).toBeGreaterThanOrEqual(64);
      } else {
        expect(bytes.toString()).toContain("<svg");
        expect(bytes.toString()).not.toMatch(/<script|<foreignObject|<image|\son\w+=/i);
      }
    }
  });

  it("uses the same Google Ads mark for the legacy account key", () => {
    expect(render("megaphone")).toBe(render("google_ads"));
  });

  it("supports compact icons and pads transparent marks", () => {
    expect(render("github", "GitHub", "sm")).toContain(styles.tileSmall);
    expect(render("github")).toContain(styles.glyphTile);
    expect(render("mail")).toContain(styles.glyphTile);
    expect(render("sentry")).toContain(styles.brandTile);
    expect(render("sentry")).not.toContain(styles.glyphTile);
  });

  it("uses a server symbol for custom MCP servers", () => {
    const html = render("server", "Custom MCP");
    expect(html).toContain("<svg");
    expect(html).not.toContain("<img");
  });

  it("keeps a stable lettered fallback for unknown providers", () => {
    const html = render("unknown", "Example");
    expect(html).toContain(">E</span>");
    expect(html).not.toContain("<img");
    expect(render("unknown", "Example")).toBe(html);
    expect(render("toString", "Example")).toBe(html);
  });
});
