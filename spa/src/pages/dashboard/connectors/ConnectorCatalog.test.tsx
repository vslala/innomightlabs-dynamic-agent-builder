import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { MCPConnection, MCPProvider } from "../../../types/connectors";
import { buildCatalog } from "./catalogItems";
import { ConnectorCatalog } from "./ConnectorCatalog";
import { ConnectorIcon } from "./ConnectorIcon";

const provider = (key: string, name: string): MCPProvider => ({
  key,
  display_name: name,
  description: `${name} things`,
  icon: key,
  docs_url: "https://example.com",
  transport: "streamable_http",
  has_inputs: false,
  has_sign_in: true,
  category: "productivity",
  featured: false,
  tags: [],
  installed_count: 0,
});

const notionInstall = {
  mcp_id: "m1",
  name: "Notion",
  server_url: "https://mcp.notion.com/mcp",
  transport: "streamable_http",
  auth_type: "oauth",
  oauth_connected: true,
  enabled: true,
  created_at: "2026-10-01T00:00:00Z",
  provider_key: "notion",
  setup_state: "ready",
  inputs: {},
} as MCPConnection;

function render(canManage: boolean, connections: MCPConnection[] = [notionInstall]) {
  const items = buildCatalog([provider("notion", "Notion"), provider("linear", "Linear")], [], connections);
  const noop = () => undefined;
  return renderToStaticMarkup(
    <ConnectorCatalog
      items={items}
      connections={connections}
      canManage={canManage}
      busyKey={null}
      onInstall={noop}
      onManage={noop}
      onManageCustom={noop}
      onAddCustom={noop}
    />
  );
}

describe("connector catalog", () => {
  it("reuses provider marks for custom servers in both Installed and Your own server", () => {
    const custom = [
      ["Notion", "https://mcp.notion.com/mcp", "notion"],
      ["Github", "https://api.githubcopilot.com/mcp/", "github"],
      ["Atlassian", "https://mcp.atlassian.com/v1/mcp/authv2", "atlassian"],
      ["Tavily Web Search Engine", "https://mcp.tavily.com/mcp/?tavilyApiKey=test", "tavily"],
      ["Cloudflare", "https://mcp.cloudflare.com/mcp", "cloudflare"],
      ["Private server", "https://custom.example/mcp", "server"],
    ];
    const connections = custom.map(([name, server_url], index) => ({
      ...notionInstall,
      mcp_id: `custom-${index}`,
      provider_key: undefined,
      name,
      server_url,
    }));
    const html = render(true, connections);
    const installed = html.split('aria-label="Installed connectors"')[1].split("</section>")[0];
    const ownServers = html.split('aria-label="Your own server"')[1].split("</section>")[0];
    for (const [name, , icon] of custom) {
      const mark = renderToStaticMarkup(<ConnectorIcon icon={icon} name={name} />).replace(/<link[^>]*>/g, "");
      expect(installed).toContain(mark);
      expect(ownServers).toContain(mark);
    }
    expect(html).toContain('aria-label="Manage Notion"');
  });
  it("offers Manage for an installed connector and Install for the rest", () => {
    const html = render(true);

    expect(html).toContain('aria-label="Manage Notion"');
    expect(html).toContain('aria-label="Install Linear"');
    expect(html).not.toContain('aria-label="Install Notion"');
    expect(html).toContain("Add your own");
  });

  it("gives read-only members no install or custom-server controls", () => {
    const html = render(false);

    expect(html).toContain('aria-label="Manage Notion"');
    expect(html).not.toContain('aria-label="Install Linear"');
    expect(html).not.toContain("Add your own");
  });
});
