import { describe, expect, it } from "vitest";

import type { ConnectorStatus, MCPConnection, MCPProvider } from "../../../types/connectors";
import { buildCatalog, buildCatalogSections, customConnections, filterCatalog, groupCatalog } from "./catalogItems";

function provider(key: string, overrides: Partial<MCPProvider> = {}): MCPProvider {
  return {
    key,
    display_name: key.toUpperCase(),
    description: `${key} description`,
    icon: key,
    docs_url: "https://example.com",
    transport: "streamable_http",
    has_inputs: false,
    has_sign_in: true,
    category: "other",
    featured: false,
    tags: [],
    installed_count: 0,
    ...overrides,
  };
}

function connection(overrides: Partial<MCPConnection>): MCPConnection {
  return {
    mcp_id: "mcp-1",
    name: "Conn",
    server_url: "https://example.com/mcp",
    transport: "streamable_http",
    auth_type: "oauth",
    oauth_connected: true,
    enabled: true,
    created_at: "2026-10-01T00:00:00Z",
    provider_key: null,
    setup_state: "ready",
    inputs: {},
    ...overrides,
  };
}

const gmail: ConnectorStatus = {
  connector_id: "gmail",
  provider_name: "Google",
  display_name: "Gmail",
  connected: false,
  connect_path: "/connectors/google/gmail",
  icon: "mail",
};

describe("buildCatalog", () => {
  it("marks a provider installed when the account has a connection for it", () => {
    const items = buildCatalog([provider("notion")], [], [connection({ provider_key: "notion" })]);

    expect(items[0]).toMatchObject({ key: "mcp:notion", installed: true, needsAttention: false });
    expect(items[0].connections).toHaveLength(1);
  });

  it("flags an install that still needs sign-in or input", () => {
    const signedOut = connection({ provider_key: "notion", oauth_connected: false, setup_state: "needs_sign_in" });

    expect(buildCatalog([provider("notion")], [], [signedOut])[0].needsAttention).toBe(true);
  });

  it("lists Google accounts as installed only when connected", () => {
    const [item] = buildCatalog([], [gmail, { ...gmail, connector_id: "drive", connected: true }], []).filter(
      (entry) => entry.google?.connector_id === "drive"
    );

    expect(item).toMatchObject({ kind: "google", installed: true });
    expect(buildCatalog([], [gmail], [])[0].installed).toBe(false);
  });
});

describe("customConnections", () => {
  it("keeps only connections without a provider", () => {
    const list = [connection({ mcp_id: "a", provider_key: "notion" }), connection({ mcp_id: "b" })];

    expect(customConnections(list).map((item) => item.mcp_id)).toEqual(["b"]);
  });
});

describe("filterCatalog", () => {
  const items = buildCatalog(
    [provider("atlassian", { display_name: "Atlassian", tags: ["jira"] }), provider("tavily", { description: "Web search" })],
    [],
    []
  );

  it("matches names, descriptions and tags without regard to case", () => {
    expect(filterCatalog(items, "ATLAS")).toHaveLength(1);
    expect(filterCatalog(items, "web")[0].name).toBe("TAVILY");
    expect(filterCatalog(items, "Jira")[0].name).toBe("Atlassian");
  });

  it("keeps everything for a blank query and nothing for no match", () => {
    expect(filterCatalog(items, "  ")).toHaveLength(2);
    expect(filterCatalog(items, "zzz")).toEqual([]);
  });
});

describe("groupCatalog", () => {
  it("puts Popular first, then categories in display order, and drops empty ones", () => {
    const items = buildCatalog(
      [
        provider("a", { category: "development", featured: true }),
        provider("b", { category: "productivity" }),
        provider("c", { category: "newcat" }),
      ],
      [],
      []
    );

    expect(groupCatalog(items).map((section) => section.id)).toEqual(["popular", "productivity", "development", "newcat"]);
    expect(groupCatalog(items)[0].items.map((item) => item.name)).toEqual(["A"]);
  });
});

describe("buildCatalogSections", () => {
  const items = buildCatalog([provider("a", { featured: true }), provider("b")], [], []);

  it("flattens matches into one Results section while searching", () => {
    expect(buildCatalogSections(items, true).map((section) => section.id)).toEqual(["results"]);
    expect(buildCatalogSections([], true)).toEqual([]);
  });

  it("groups the catalog when not searching", () => {
    expect(buildCatalogSections(items, false)[0].id).toBe("popular");
  });
});
