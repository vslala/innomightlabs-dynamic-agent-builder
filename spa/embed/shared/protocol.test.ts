import { describe, expect, it } from "vitest";

import { decodeConfig, encodeConfig, envelope, isEmbedMessage, type EmbedConfig } from "./protocol";

describe("embed config fragment", () => {
  it("round-trips through the iframe URL fragment", () => {
    const config: EmbedConfig = { mode: "inline", theme: "dark", primaryColor: "#ff5500", greeting: "Hi & welcome #1" };

    expect(decodeConfig(`#${encodeConfig(config)}`)).toEqual(config);
  });

  it("falls back to defaults for a missing or malformed fragment", () => {
    expect(decodeConfig("")).toEqual({ mode: "floating", theme: "auto" });
    expect(decodeConfig("#not-json")).toEqual({ mode: "floating", theme: "auto" });
  });

  it("rejects unknown mode and theme values", () => {
    const fragment = encodeURIComponent(JSON.stringify({ mode: "popover", theme: "neon" }));

    expect(decodeConfig(fragment)).toMatchObject({ mode: "floating", theme: "auto" });
  });
});

describe("embed messages", () => {
  it("recognises its own envelope only", () => {
    expect(isEmbedMessage(envelope({ type: "ready" }))).toBe(true);
    expect(isEmbedMessage({ type: "ready" })).toBe(false);
    expect(isEmbedMessage({ ...envelope({ type: "ready" }), v: 2 })).toBe(false);
    expect(isEmbedMessage("innomight-embed")).toBe(false);
    expect(isEmbedMessage(null)).toBe(false);
  });
});
