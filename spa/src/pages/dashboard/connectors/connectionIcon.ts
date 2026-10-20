import type { MCPConnection } from "../../../types/connectors";

const MCP_HOST_ICONS: Record<string, string> = {
  "mcp.notion.com": "notion",
  "api.githubcopilot.com": "github",
  "mcp.atlassian.com": "atlassian",
  "mcp.tavily.com": "tavily",
  "mcp.cloudflare.com": "cloudflare",
  "mcp.linear.app": "linear",
  "mcp.canva.com": "canva",
  "mcp.context7.com": "context7",
  "mcp.sentry.dev": "sentry",
  "mcp.supabase.com": "supabase",
};

/** Recognize hand-added providers without changing their install or authorization behavior. */
export function connectionIcon(connection: Pick<MCPConnection, "provider_key" | "server_url">): string {
  if (connection.provider_key) return connection.provider_key;
  try {
    const url = new URL(connection.server_url);
    if (url.protocol !== "https:" && url.protocol !== "http:") return "server";
    return Object.hasOwn(MCP_HOST_ICONS, url.hostname) ? MCP_HOST_ICONS[url.hostname] : "server";
  } catch {
    return "server";
  }
}
