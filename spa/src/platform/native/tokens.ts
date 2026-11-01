import { ApiRequestError, apiPost } from "../api";
import type { Session, TokenStore } from "../types";

/** Where the long-lived credential lives: the Keychain or Keystore (see vault.ts). */
export interface Vault {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
  remove(key: string): Promise<void>;
}

/** The pair `/auth/native/token` and `/auth/native/refresh` answer with. */
export interface NativeTokenResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

const SESSION_KEY = "session";
/** Refresh this close to expiry rather than wait for a 401 (LLD: within five minutes). */
const REFRESH_MARGIN_MS = 5 * 60 * 1000;

interface StoredSession {
  userId: string;
  refreshToken: string;
}

export interface NativeTokens extends TokenStore {
  /** Reads the stored session; called once by ready(). */
  load(): Promise<void>;
  /** True when there is a session but no access token, or one about to expire. */
  needsRefresh(now?: number): boolean;
  /** Ends this device's session on the server (best effort): it proves possession of the refresh token. */
  revoke(): Promise<void>;
}

/**
 * The app's credentials: the access token only in memory, the refresh token (with the user it belongs to) in the
 * vault. Refreshes are single-flight, so a burst of 401s rotates the refresh token once.
 */
export function createNativeTokens(vault: Vault, deviceId: () => string): NativeTokens {
  let access: string | null = null;
  let expiresAt = 0;
  let session: StoredSession | null = null;
  let inflight: Promise<string | null> | null = null;

  const forget = async () => {
    access = null;
    expiresAt = 0;
    session = null;
    await vault.remove(SESSION_KEY);
  };

  const save = async ({ accessToken, refreshToken, expiresIn }: Session) => {
    access = accessToken;
    expiresAt = expiresIn ? Date.now() + expiresIn * 1000 : 0;
    if (refreshToken) {
      session = { userId: subjectOf(accessToken), refreshToken };
      await vault.set(SESSION_KEY, JSON.stringify(session));
    }
  };

  const refreshOnce = async (): Promise<string | null> => {
    if (!session) return null;
    try {
      const pair = await apiPost<NativeTokenResponse>("/auth/native/refresh", {
        user_id: session.userId,
        device_id: deviceId(),
        refresh_token: session.refreshToken,
      });
      await save(sessionFrom(pair));
      return access;
    } catch (err) {
      // Refused (expired, reused, account gone): signed out. Anything else (offline) keeps the session for later.
      if (err instanceof ApiRequestError && err.status === 401) await forget();
      return null;
    }
  };

  return {
    accessToken: () => access,
    refresh: () => {
      inflight ??= refreshOnce().finally(() => {
        inflight = null;
      });
      return inflight;
    },
    save,
    clear: forget,
    load: async () => {
      const stored = await vault.get(SESSION_KEY);
      session = stored ? parseSession(stored) : null;
    },
    needsRefresh: (now = Date.now()) => session !== null && (!access || (expiresAt > 0 && expiresAt - now < REFRESH_MARGIN_MS)),
    revoke: async () => {
      if (!session) return;
      try {
        await apiPost("/auth/native/revoke", { user_id: session.userId, device_id: deviceId(), refresh_token: session.refreshToken });
      } catch {
        // Signing out still happens on this device; the server's copy expires on its own.
      }
    },
  };
}

export function sessionFrom(pair: NativeTokenResponse): Session {
  return { accessToken: pair.access_token, refreshToken: pair.refresh_token, expiresIn: pair.expires_in };
}

/** The user id (`sub`) of an owner JWT. The payload is read, not verified: the API verifies. */
function subjectOf(token: string): string {
  const payload = token.split(".")[1] ?? "";
  const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
  return String((JSON.parse(json) as { sub?: unknown }).sub ?? "");
}

function parseSession(stored: string): StoredSession | null {
  try {
    const value = JSON.parse(stored) as Partial<StoredSession>;
    return value.userId && value.refreshToken ? { userId: value.userId, refreshToken: value.refreshToken } : null;
  } catch {
    return null;
  }
}
