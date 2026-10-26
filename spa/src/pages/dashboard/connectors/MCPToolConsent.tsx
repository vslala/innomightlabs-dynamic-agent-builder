import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";

import { Button, Switch } from "../../../components/ui";
import { connectorApiService } from "../../../services/connectors";
import type { MCPToolPolicy } from "../../../types/connectors";
import styles from "./ConnectorCatalog.module.css";

/**
 * Which of a connection's tools show the agent's owner the exact call to approve before they run. Until someone
 * chooses, the tools the server marks destructive ask. See docs/LLD-action-consent.md.
 */
export function MCPToolConsent({ mcpId, canManage }: { mcpId: string; canManage: boolean }) {
  const [policy, setPolicy] = useState<MCPToolPolicy | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    connectorApiService
      .getMCPToolPolicy(mcpId)
      .then((loaded) => !cancelled && setPolicy(loaded))
      .catch((err) => console.error("Failed to load which tools ask first:", err));
    return () => {
      cancelled = true;
    };
  }, [mcpId]);

  const run = async (action: () => Promise<MCPToolPolicy>) => {
    setBusy(true);
    setError(null);
    try {
      setPolicy(await action());
    } catch (err) {
      setError(err instanceof Error ? err.message : "That didn't save. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const listTools = () =>
    run(async () => {
      await connectorApiService.refreshMCPToolCatalog(mcpId);
      return connectorApiService.getMCPToolPolicy(mcpId);
    });

  const setAsks = (name: string, asks: boolean) => {
    if (!policy) return;
    const chosen = policy.tools.filter((tool) => (tool.name === name ? asks : tool.asks_first)).map((tool) => tool.name);
    void run(() => connectorApiService.setMCPToolPolicy(mcpId, chosen));
  };

  if (!policy) return null;

  return (
    <details className={styles.toolConsent}>
      <summary>
        Ask before running
        <small>
          {policy.tools.filter((tool) => tool.asks_first).length} of {policy.tools.length} tools
          {policy.chosen ? "" : " · destructive tools by default"}
        </small>
      </summary>
      <p className={styles.toolConsentHint}>
        A tool that asks first shows you the exact call to approve before an agent runs it. Only you can use it: people
        you share an agent with don't get it.
      </p>
      {error && <p className={styles.toolConsentError}>{error}</p>}
      {policy.tools.length === 0 ? (
        <Button size="sm" variant="outline" disabled={busy || !canManage} onClick={() => void listTools()}>
          <RefreshCw className="h-4 w-4" />
          List its tools
        </Button>
      ) : (
        <ul className={styles.toolConsentList}>
          {policy.tools.map((tool) => (
            <li key={tool.name}>
              <span>
                {tool.title || tool.name}
                <small>{tool.read_only ? "reads only" : tool.destructive ? "may change or delete" : "may change"}</small>
              </span>
              <Switch
                checked={tool.asks_first}
                disabled={busy || !canManage}
                aria-label={`Ask before running ${tool.title || tool.name}`}
                onCheckedChange={(checked) => setAsks(tool.name, checked)}
              />
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}
