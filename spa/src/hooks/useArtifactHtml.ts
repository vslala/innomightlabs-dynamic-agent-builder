import { useEffect, useState } from "react";

export type ArtifactHtmlState =
  | { status: "loading" }
  | { status: "loaded"; html: string }
  | { status: "failed" };

/**
 * Fetches an artifact's raw text content (e.g. a canvas artifact's HTML) from the
 * authenticated backend content-proxy endpoint. `enabled` gates the fetch so callers
 * can lazy-load (e.g. only once a card scrolls near the viewport).
 */
export function useArtifactHtml(contentUrl: string | null | undefined, enabled: boolean): ArtifactHtmlState {
  const [state, setState] = useState<ArtifactHtmlState>({ status: "loading" });

  useEffect(() => {
    if (!enabled || !contentUrl) return;
    let active = true;
    setState({ status: "loading" });

    async function load() {
      try {
        const token = localStorage.getItem("auth_token");
        const response = await fetch(contentUrl!, {
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        });
        if (!response.ok) throw new Error(`Canvas request failed with ${response.status}`);
        const html = await response.text();
        if (active) setState({ status: "loaded", html });
      } catch {
        if (active) setState({ status: "failed" });
      }
    }

    void load();
    return () => {
      active = false;
    };
  }, [contentUrl, enabled]);

  return state;
}
