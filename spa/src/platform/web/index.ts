import { API_BASE_URL, apiPost } from "../api";
import type { KeyValueStore, LoginProvider, Platform } from "../types";
import { createWebTokens } from "./tokens";

/** The chat card's sign-in window: one named popup, reused if the person clicks again. */
const POPUP_NAME = "innomight-connect";
const POPUP_FEATURES = "popup,width=520,height=720";

/** Where the API starts sign-in for a provider; an invitation's login context rides along when there is one. */
export function loginUrl(provider: LoginProvider, invitation?: string, baseUrl = API_BASE_URL): string {
  const start = `${baseUrl.replace(/\/$/, "")}/auth/${provider}`;
  return invitation ? `${start}?invitation=${encodeURIComponent(invitation)}` : start;
}

/** The browser: today's behaviour, behind the ports. */
export function createWebPlatform(): Platform {
  const tokens = createWebTokens();
  const storage = createWebStorage();

  return {
    kind: "web",
    tokens,
    storage,
    auth: {
      begin: async (provider, options) => {
        window.location.href = loginUrl(provider, options?.invitation);
      },
      complete: async (code) => {
        const { token } = await apiPost<{ token: string }>("/auth/session", { code });
        await tokens.save({ accessToken: token });
        // A new session starts in the account the API remembers, not the one the last person chose here.
        storage.remove("active_account_id");
      },
      // The web token is stateless: there is no server session to end.
      end: () => tokens.clear(),
    },
    links: {
      returnTo: (path) => `${window.location.origin}${path}`,
      openAuthPage: async (url, options) => {
        if (options?.popup) return window.open(url, POPUP_NAME, POPUP_FEATURES) !== null;
        window.location.assign(url);
        return true;
      },
      openExternal: async (url) => {
        window.open(url, "_blank", "noopener,noreferrer");
      },
      // Returns reach the web as ordinary page loads (`/dashboard/...?oauth_complete=`), never as app links.
      onAppLink: () => () => {},
    },
    lifecycle: {
      onResume: (handler) => {
        const onVisibility = () => {
          if (document.visibilityState === "visible") handler();
        };
        document.addEventListener("visibilitychange", onVisibility);
        return () => document.removeEventListener("visibilitychange", onVisibility);
      },
    },
    files: {
      saveOrShare: async ({ data, filename }) => {
        const url = URL.createObjectURL(data);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = filename;
        anchor.click();
        // Let the download start before the URL goes away.
        setTimeout(() => URL.revokeObjectURL(url), 0);
      },
    },
    push: null,
    commerce: { canSellSubscriptions: true },
    ready: async () => {},
  };
}

/** localStorage, read straight through. Storage can be blocked (private mode, embedded frames): then nothing is kept. */
function createWebStorage(): KeyValueStore {
  return {
    get: (key) => {
      try {
        return localStorage.getItem(key);
      } catch {
        return null;
      }
    },
    set: (key, value) => {
      try {
        localStorage.setItem(key, value);
      } catch {
        // Not remembered.
      }
    },
    remove: (key) => {
      try {
        localStorage.removeItem(key);
      } catch {
        // Nothing was kept.
      }
    },
  };
}
