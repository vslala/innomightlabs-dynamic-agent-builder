import { httpClient } from "../http";

/** The query parameter a connect flow's return address carries its sealed handoff in. */
export const HANDOFF_PARAM = "oauth_complete";

/**
 * Completes a connect flow's sealed handoff, signed in, and returns the result parameters the pages read
 * (e.g. `{ mcp_oauth: "success", mcp_id: "…" }`). Completing it is what proves the connection belongs to whoever
 * started it. A failed completion reads as `{ skill_oauth: "error" }`, which every connect page shows as an error.
 */
export async function completeOAuthHandoff(completion: string): Promise<Record<string, string>> {
  try {
    const { result } = await httpClient.post<{ result: Record<string, string> }>("/connectors/oauth/complete", { completion });
    return result;
  } catch {
    return { skill_oauth: "error" };
  }
}
