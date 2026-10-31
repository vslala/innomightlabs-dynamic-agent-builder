import type { TokenStore } from "../types";

const AUTH_TOKEN_KEY = "auth_token";

/**
 * The web keeps today's 7-day owner token in localStorage, read on every request so another tab's sign-in or
 * sign-out is seen. There is no refresh token on the web, so a 401 means signed out.
 */
export function createWebTokens(): TokenStore {
  return {
    accessToken: () => localStorage.getItem(AUTH_TOKEN_KEY),
    refresh: async () => null,
    save: async ({ accessToken }) => localStorage.setItem(AUTH_TOKEN_KEY, accessToken),
    clear: async () => localStorage.removeItem(AUTH_TOKEN_KEY),
  };
}
