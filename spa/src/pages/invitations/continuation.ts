export const PENDING_INVITATION_KEY = "pendingInvitationToken";

export interface InvitationBootstrap {
  token: string | null;
  error?: string;
}

// Run synchronously before rendering: StrictMode's second render reads the saved
// token, not the fragment that the first render already removed.
export function captureInvitationToken(
  location: Pick<Location, "hash" | "pathname" | "search">,
  history: Pick<History, "replaceState" | "state">,
  storage: Pick<Storage, "getItem" | "setItem"> | (() => Pick<Storage, "getItem" | "setItem">),
): InvitationBootstrap {
  const params = new URLSearchParams(location.hash.replace(/^#/, ""));
  const incoming = params.get("token");
  if (params.has("token")) {
    // Cleanup must happen even if session storage is blocked.
    history.replaceState(history.state, "", location.pathname + location.search);
  }
  const storageError = "Invitation storage is unavailable. Enable session storage in this browser and reopen the invitation link.";
  if (new URLSearchParams(location.search).get("invitation_storage_error") === "1") {
    return { token: null, error: storageError };
  }
  try {
    const session = typeof storage === "function" ? storage() : storage;
    if (incoming) session.setItem(PENDING_INVITATION_KEY, incoming);
    return { token: incoming || session.getItem(PENDING_INVITATION_KEY) };
  } catch {
    const search = new URLSearchParams(location.search);
    search.set("invitation_storage_error", "1");
    history.replaceState(history.state, "", `${location.pathname}?${search.toString()}`);
    return { token: null, error: storageError };
  }
}

export function invitationLoginUrl(provider: "google" | "cognito", loginContext: string, baseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"): string {
  return `${baseUrl.replace(/\/$/, "")}/auth/${provider}?invitation=${encodeURIComponent(loginContext)}`;
}

export function isInvitationContinuation(params: URLSearchParams): boolean {
  return params.get("invitation") === "1";
}
