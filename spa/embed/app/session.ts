/**
 * The signed-in visitor, kept in the iframe's own storage. Browsers partition
 * that storage by the embedding site, so each site keeps its own sign-in and
 * the host page can never read the token.
 */

export interface Visitor {
  visitorId: string;
  email: string;
  name?: string | null;
  picture?: string | null;
}

export interface Session {
  token: string;
  refreshToken?: string | null;
  visitor: Visitor;
}

/** Refresh this long before the visitor token expires. */
const REFRESH_MARGIN_MS = 5 * 60 * 1000;

function safeStorage(): Pick<Storage, "getItem" | "setItem" | "removeItem"> {
  try {
    const probe = "__innomight_probe__";
    window.localStorage.setItem(probe, probe);
    window.localStorage.removeItem(probe);
    return window.localStorage;
  } catch {
    // Storage blocked (e.g. strict third-party settings): keep the session for this page view only.
    const memory = new Map<string, string>();
    return {
      getItem: (key) => memory.get(key) ?? null,
      setItem: (key, value) => void memory.set(key, value),
      removeItem: (key) => void memory.delete(key),
    };
  }
}

const storage = safeStorage();

const sessionKey = (publicKey: string) => `innomight-embed:${publicKey}:session`;
/** One JSON map of chat scope → current conversation, so sign-out clears them all at once. */
const conversationsKey = (publicKey: string) => `innomight-embed:${publicKey}:conversations`;

/**
 * Which "current conversation" a chat resumes. Chats with a default prompt each keep their own,
 * so every section of a page picks up its own thread; plain chats share one.
 */
export function conversationScope(prompt: string | undefined): string {
  if (!prompt) return "default";
  let hash = 5381;
  for (let i = 0; i < prompt.length; i++) hash = ((hash << 5) + hash + prompt.charCodeAt(i)) | 0;
  return `prompt-${(hash >>> 0).toString(36)}`;
}

function loadConversationIds(publicKey: string): Record<string, string> {
  try {
    return (JSON.parse(storage.getItem(conversationsKey(publicKey)) ?? "{}") as Record<string, string>) ?? {};
  } catch {
    return {};
  }
}

export function loadSession(publicKey: string): Session | null {
  try {
    const session = JSON.parse(storage.getItem(sessionKey(publicKey)) ?? "null") as Session | null;
    return session?.token && session.visitor ? session : null;
  } catch {
    return null;
  }
}

export function saveSession(publicKey: string, session: Session): void {
  storage.setItem(sessionKey(publicKey), JSON.stringify(session));
}

export function clearSession(publicKey: string): void {
  storage.removeItem(sessionKey(publicKey));
  storage.removeItem(conversationsKey(publicKey));
}

export function loadConversationId(publicKey: string, scope: string): string | null {
  return loadConversationIds(publicKey)[scope] ?? null;
}

/** Conversations other chats on this site are using, so a plain chat doesn't resume one of them. */
export function conversationIdsOutside(publicKey: string, scope: string): Set<string> {
  return new Set(
    Object.entries(loadConversationIds(publicKey))
      .filter(([otherScope]) => otherScope !== scope)
      .map(([, conversationId]) => conversationId)
  );
}

export function saveConversationId(publicKey: string, scope: string, conversationId: string | null): void {
  const ids = loadConversationIds(publicKey);
  if (conversationId) ids[scope] = conversationId;
  else delete ids[scope];
  storage.setItem(conversationsKey(publicKey), JSON.stringify(ids));
}

/** Expiry of a JWT in epoch ms, or null when it can't be read. */
export function tokenExpiresAt(token: string): number | null {
  try {
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))) as { exp?: number };
    return typeof payload.exp === "number" ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

export function needsRefresh(token: string, now: number = Date.now()): boolean {
  const expiresAt = tokenExpiresAt(token);
  return expiresAt === null || expiresAt - now < REFRESH_MARGIN_MS;
}
