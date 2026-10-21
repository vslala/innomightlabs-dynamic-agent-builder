import { describe, expect, it } from "vitest";

import { connectorsTabFromSearch } from "./connectorUrls";

describe("connectorsTabFromSearch", () => {
  it("opens the Social tab when asked", () => {
    expect(connectorsTabFromSearch("?tab=social")).toBe("social");
    expect(connectorsTabFromSearch("?foo=1&tab=social&social_oauth=success")).toBe("social");
  });

  it("opens the MCPs tab otherwise", () => {
    expect(connectorsTabFromSearch("")).toBe("mcp");
    expect(connectorsTabFromSearch("?tab=mcp")).toBe("mcp");
    expect(connectorsTabFromSearch("?tab=nonsense")).toBe("mcp");
  });
});
