import type { LoginProvider, Platform, Session, StorageKey } from "./types";

export interface FakePlatform extends Platform {
  /** Every URL handed to `links.openAuthPage` or `links.openExternal`, in order. */
  readonly opened: string[];
  /** The providers `auth.begin` was asked for. */
  readonly begun: LoginProvider[];
  readonly values: Map<StorageKey, string>;
  /** Fires the `lifecycle.onResume` handlers, as the tab or app coming back would. */
  resume(): void;
}

/**
 * An in-memory platform for tests: services, hooks and the HTTP client are tested against the ports without
 * either adapter. Pass `overrides` to replace a whole port.
 */
export function createFakePlatform(
  overrides: Partial<Platform> = {},
  { accessToken = null as string | null } = {},
): FakePlatform {
  const opened: string[] = [];
  const begun: LoginProvider[] = [];
  const values = new Map<StorageKey, string>();
  const resumeHandlers = new Set<() => void>();
  let token = accessToken;

  return {
    kind: "web",
    opened,
    begun,
    values,
    resume: () => resumeHandlers.forEach((handler) => handler()),
    auth: {
      begin: async (provider) => {
        begun.push(provider);
      },
      complete: async (code) => {
        token = `token-for-${code}`;
      },
      end: async () => {
        token = null;
      },
    },
    tokens: {
      accessToken: () => token,
      refresh: async () => null,
      save: async (session: Session) => {
        token = session.accessToken;
      },
      clear: async () => {
        token = null;
      },
    },
    links: {
      returnTo: (path) => `https://app.test${path}`,
      openAuthPage: async (url) => {
        opened.push(url);
        return true;
      },
      openExternal: async (url) => {
        opened.push(url);
      },
      onAppLink: () => () => {},
    },
    storage: {
      get: (key) => values.get(key) ?? null,
      set: (key, value) => void values.set(key, value),
      remove: (key) => void values.delete(key),
    },
    lifecycle: {
      onResume: (handler) => {
        resumeHandlers.add(handler);
        return () => void resumeHandlers.delete(handler);
      },
    },
    files: { saveOrShare: async () => {} },
    push: null,
    commerce: { canSellSubscriptions: true },
    ready: async () => {},
    ...overrides,
  };
}
