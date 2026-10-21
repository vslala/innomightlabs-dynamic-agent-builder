/** Where provider and MCP OAuth flows return after sign-in; `tab` picks the Connectors tab they land on. */
export function returnToConnectors(tab?: "social"): string {
  return `${window.location.origin}/dashboard/connectors${tab ? `?tab=${tab}` : ""}`;
}

export type ConnectorsTab = "mcp" | "social";

/** The tab a Connectors URL asks for (`?tab=social`); anything else is the MCPs tab. */
export function connectorsTabFromSearch(search: string): ConnectorsTab {
  return new URLSearchParams(search).get("tab") === "social" ? "social" : "mcp";
}
