import { Browser } from "@capacitor/browser";
import { API_BASE_URL, apiPost } from "../api";
import { challengeFor, createVerifier } from "../pkce";
import type { AuthSession, KeyValueStore } from "../types";
import { sessionFrom, type NativeTokenResponse, type NativeTokens } from "./tokens";

/** The API's name for the store apps: a public client, so PKCE stands in for a client secret. */
const NATIVE_APP = "mobile";

/**
 * Sign-in in the system browser (RFC 8252). The verifier is kept in Preferences, not memory, because iOS may
 * end the app while the person is in the browser; the login code arrives later as an `auth` app link.
 */
export function createNativeAuth(tokens: NativeTokens, storage: KeyValueStore, deviceId: () => string): AuthSession {
  return {
    // Invitations are accepted on the website (the API keeps them on the web app), so `invitation` is not sent.
    begin: async (provider) => {
      const verifier = createVerifier();
      storage.set("pkce_verifier", verifier);
      const query = new URLSearchParams({
        app: NATIVE_APP,
        code_challenge: await challengeFor(verifier),
        code_challenge_method: "S256",
      });
      await Browser.open({ url: `${API_BASE_URL.replace(/\/$/, "")}/auth/${provider}?${query}` });
    },
    complete: async (code) => {
      const verifier = storage.get("pkce_verifier");
      if (!verifier) throw new Error("No sign-in is waiting for this code");
      try {
        const pair = await apiPost<NativeTokenResponse>("/auth/native/token", {
          code,
          code_verifier: verifier,
          device_id: deviceId(),
        });
        await tokens.save(sessionFrom(pair));
        storage.remove("active_account_id");
      } finally {
        storage.remove("pkce_verifier");
      }
    },
    end: async () => {
      await tokens.revoke();
      await tokens.clear();
    },
  };
}
