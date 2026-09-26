/** Where provider and MCP OAuth flows return after sign-in. */
export function returnToConnectors(): string {
  return `${window.location.origin}/dashboard/connectors`;
}
