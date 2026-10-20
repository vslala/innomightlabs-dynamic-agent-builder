import type { ConnectorStatus, MCPConnection, MCPProvider } from "../../../types/connectors";

/** Section order on the page. Categories the backend adds later are listed after these, alphabetically. */
const CATEGORY_ORDER = ["productivity", "development", "marketing", "payments", "search", "design", "other"];

const GOOGLE_TAGS: Record<string, string[]> = {
  mail: ["email", "inbox", "google"],
  hard_drive: ["files", "docs", "sheets", "slides", "google"],
};

/** One row on the page: a Google account or an MCP provider, with whatever the account has installed of it. */
export interface CatalogItem {
  key: string;
  kind: "mcp" | "google";
  name: string;
  description: string;
  icon: string;
  category: string;
  featured: boolean;
  tags: string[];
  installed: boolean;
  needsAttention: boolean;
  provider?: MCPProvider;
  connections: MCPConnection[];
  google?: ConnectorStatus;
}

export interface CatalogSectionData {
  id: string;
  title: string;
  items: CatalogItem[];
}

function connectionNeedsAttention(connection: MCPConnection): boolean {
  if (connection.provider_key && connection.setup_state !== "ready") return true;
  return connection.auth_type === "oauth" && !connection.oauth_connected;
}

export function buildCatalog(
  providers: MCPProvider[],
  google: ConnectorStatus[],
  connections: MCPConnection[]
): CatalogItem[] {
  const providerItems = providers.map((provider): CatalogItem => {
    const own = connections.filter((connection) => connection.provider_key === provider.key);
    return {
      key: `mcp:${provider.key}`,
      kind: "mcp",
      name: provider.display_name,
      description: provider.description,
      icon: provider.icon,
      category: provider.category,
      featured: provider.featured,
      tags: provider.tags,
      installed: own.length > 0,
      needsAttention: own.some(connectionNeedsAttention),
      provider,
      connections: own,
    };
  });
  const googleItems = google.map(
    (connector): CatalogItem => ({
      key: `google:${connector.connector_id}`,
      kind: "google",
      name: connector.display_name,
      description: "Lets agents and automations use your Google account.",
      icon: connector.icon,
      category: "productivity",
      featured: true,
      tags: GOOGLE_TAGS[connector.icon] ?? ["google"],
      installed: connector.connected,
      needsAttention: false,
      connections: [],
      google: connector,
    })
  );
  return [...googleItems, ...providerItems];
}

/** Servers the account added by hand: they belong to no catalog entry. */
export function customConnections(connections: MCPConnection[]): MCPConnection[] {
  return connections.filter((connection) => !connection.provider_key);
}

/** Case-insensitive match over name, description and tags; an empty query keeps everything. */
export function filterCatalog(items: CatalogItem[], query: string): CatalogItem[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return items;
  return items.filter((item) =>
    [item.name, item.description, ...item.tags].some((text) => text.toLowerCase().includes(needle))
  );
}

function categoryTitle(category: string): string {
  return category.charAt(0).toUpperCase() + category.slice(1);
}

function categoryRank(category: string): number {
  const rank = CATEGORY_ORDER.indexOf(category);
  return rank === -1 ? CATEGORY_ORDER.length - 1 : rank;
}

/** "Popular" first, then one section per category. Empty sections are dropped. */
export function groupCatalog(items: CatalogItem[]): CatalogSectionData[] {
  const byCategory = new Map<string, CatalogItem[]>();
  for (const item of items) byCategory.set(item.category, [...(byCategory.get(item.category) ?? []), item]);
  const categories = [...byCategory.keys()].sort(
    (a, b) => categoryRank(a) - categoryRank(b) || a.localeCompare(b)
  );
  const popular = items.filter((item) => item.featured);
  return [
    { id: "popular", title: "Popular", items: popular },
    ...categories.map((category) => ({
      id: category,
      title: categoryTitle(category),
      items: byCategory.get(category) ?? [],
    })),
  ].filter((section) => section.items.length > 0);
}

/** While searching, one flat list of matches; otherwise the grouped catalog. */
export function buildCatalogSections(items: CatalogItem[], searching: boolean): CatalogSectionData[] {
  if (!searching) return groupCatalog(items);
  return items.length > 0 ? [{ id: "results", title: "Results", items }] : [];
}
