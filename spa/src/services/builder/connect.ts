/**
 * Connecting an account from Ada's chat: the sign-in runs in a popup, and the popup tells the chat how it went.
 * See docs/LLD-ada-capabilities.md.
 */

/** The message the popup's return page posts to the chat window. */
export const OAUTH_MESSAGE_TYPE = "innomight:oauth";

export interface OAuthPopupMessage {
  type: typeof OAUTH_MESSAGE_TYPE;
  /** The result parameters the sign-in completed with, e.g. { mcp_oauth: "success", mcp_id: "…" }. */
  result: Record<string, string>;
}

export type ConnectOutcome = "connected" | "failed";

/**
 * How a sign-in went, from a window message. Only our own origin's popup is believed; anything else is ignored
 * (null), so another page can't claim an account is connected.
 */
export function connectOutcome(event: { origin: string; data: unknown }, ownOrigin: string): ConnectOutcome | null {
  if (event.origin !== ownOrigin) return null;
  const data = event.data as Partial<OAuthPopupMessage> | null;
  if (!data || data.type !== OAUTH_MESSAGE_TYPE || !data.result) return null;
  const succeeded = Object.entries(data.result).some(([key, value]) => key.endsWith("_oauth") && value === "success");
  return succeeded ? "connected" : "failed";
}

/** What the chat says for the person once they're connected. Ada plans again on it; the plan checks for itself. */
export function connectedMessage(title: string): string {
  return `I've connected ${title.replace(/^Connect\s+/, "")}.`;
}
