import { describe, expect, it } from "vitest";

import { connectionIcon } from "./connectionIcon";

describe("MCP connection icons", () => {
  it.each([
    ["https://mcp.notion.com/mcp", "notion"],
    ["https://api.githubcopilot.com/mcp/", "github"],
    ["https://mcp.atlassian.com/v1/mcp/authv2", "atlassian"],
    ["https://mcp.atlassian.com/v2/mcp", "atlassian"],
    ["https://mcp.tavily.com/mcp/?tavilyApiKey=test", "tavily"],
    ["https://mcp.cloudflare.com/mcp", "cloudflare"],
    ["https://mcp.linear.app/sse", "linear"],
    ["https://mcp.canva.com/mcp", "canva"],
    ["https://mcp.context7.com/mcp", "context7"],
    ["https://mcp.sentry.dev/mcp", "sentry"],
    ["https://mcp.supabase.com/mcp?project_ref=test", "supabase"],
    ["https://MCP.NOTION.COM:443/mcp", "notion"],
  ])("recognizes %s as %s", (server_url, icon) => {
    expect(connectionIcon({ server_url })).toBe(icon);
  });

  it("prefers explicit provider metadata", () => {
    expect(connectionIcon({ provider_key: "google_ads", server_url: "" })).toBe("google_ads");
  });

  it.each([
    "https://custom.example/mcp",
    "https://mcp.notion.com.example/mcp",
    "https://mcp.notion.com@custom.example/mcp",
    "https://custom.example/mcp?url=https://mcp.notion.com",
    "https://toString/mcp",
    "file://mcp.notion.com/mcp",
    "invalid URL",
    "",
  ])("keeps the server fallback for %s", (server_url) => {
    expect(connectionIcon({ server_url })).toBe("server");
  });
});
