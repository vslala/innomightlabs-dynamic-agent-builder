import { useCallback, useEffect, useState } from "react";
import { RotateCcw } from "lucide-react";

import { Button, StatusBadge } from "../../../components/ui";
import { connectorApiService } from "../../../services/connectors";
import type { MCPRuntimeState, MCPRuntimeStatus } from "../../../types/connectors";

const POLL_INTERVAL_MS = 2000;

const STATE_BADGES: Record<MCPRuntimeState, { status: "active" | "in_progress" | "failed" | "inactive"; label: string }> = {
  running: { status: "active", label: "Running" },
  starting: { status: "in_progress", label: "Starting" },
  failed: { status: "failed", label: "Failed" },
  stopped: { status: "inactive", label: "Stopped" },
};

/** Runtime of a hosted stdio connector: status, why it failed, and a restart. Polls while starting. */
export function MCPRuntimeStatus({ mcpId, canStart }: { mcpId: string; canStart: boolean }) {
  const [status, setStatus] = useState<MCPRuntimeStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [restarting, setRestarting] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setStatus(await connectorApiService.getMCPRuntime(mcpId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load runtime status.");
    }
  }, [mcpId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (status?.state !== "starting") return;
    const timer = window.setInterval(() => void refresh(), POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [status?.state, refresh]);

  const restart = async () => {
    setRestarting(true);
    setError(null);
    try {
      setStatus(await connectorApiService.restartMCPRuntime(mcpId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start the MCP server.");
    } finally {
      setRestarting(false);
    }
  };

  const badge = status ? STATE_BADGES[status.state] : null;
  const serverName = typeof status?.server_info?.name === "string" ? status.server_info.name : null;

  return (
    <div style={{ display: "grid", gap: "0.5rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
        <span style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Runtime:</span>
        {badge && <StatusBadge status={badge.status} label={badge.label} size="sm" />}
        {serverName && status?.state === "running" && (
          <span style={{ color: "var(--text-muted)", fontSize: "0.8125rem" }}>{serverName}</span>
        )}
        {canStart && (
          <Button type="button" variant="outline" size="sm" onClick={() => void restart()} disabled={restarting}>
            <RotateCcw className="h-4 w-4" />
            {restarting ? "Starting..." : status?.state === "running" ? "Restart" : "Start"}
          </Button>
        )}
      </div>
      {status?.state === "failed" && status.error && (
        <p style={{ color: "var(--error)", fontSize: "0.8125rem", overflowWrap: "anywhere" }}>{status.error}</p>
      )}
      {status?.state === "failed" && status.stderr_tail && (
        <details>
          <summary style={{ color: "var(--text-muted)", fontSize: "0.8125rem", cursor: "pointer" }}>Server output</summary>
          <pre
            style={{
              marginTop: "0.5rem",
              maxHeight: "12rem",
              overflow: "auto",
              fontSize: "0.75rem",
              whiteSpace: "pre-wrap",
              color: "var(--text-muted)",
            }}
          >
            {status.stderr_tail}
          </pre>
        </details>
      )}
      {error && <p style={{ color: "var(--error)", fontSize: "0.8125rem" }}>{error}</p>}
    </div>
  );
}
