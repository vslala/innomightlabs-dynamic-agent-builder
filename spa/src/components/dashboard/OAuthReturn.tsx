import { useEffect, useRef, useState, type ReactNode } from "react";

import { LoadingState } from "../ui";
import { httpClient } from "../../services/http";

const HANDOFF_PARAM = "oauth_complete";

/**
 * Connect flows (Gmail, Drive, Ads, MCP, remote agents) come back from the provider with a sealed
 * handoff instead of a finished connection. Completing it here, signed in, is what proves the
 * connection belongs to whoever started it. The result replaces the handoff in the URL as the
 * parameters the page already reads, so the page renders only once it is done.
 */
export function OAuthReturn({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState(() => new URLSearchParams(window.location.search).has(HANDOFF_PARAM));
  const started = useRef(false);

  useEffect(() => {
    if (!pending || started.current) return;
    started.current = true;

    const params = new URLSearchParams(window.location.search);
    const completion = params.get(HANDOFF_PARAM) ?? "";
    params.delete(HANDOFF_PARAM);

    httpClient
      .post<{ result: Record<string, string> }>("/connectors/oauth/complete", { completion })
      .then(({ result }) => Object.entries(result).forEach(([key, value]) => params.set(key, value)))
      .catch(() => params.set("skill_oauth", "error"))
      .finally(() => {
        const query = params.toString();
        window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
        setPending(false);
      });
  }, [pending]);

  return pending ? <LoadingState /> : <>{children}</>;
}
