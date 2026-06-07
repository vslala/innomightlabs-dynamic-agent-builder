import { useEffect, useMemo, useState } from "react";
import { CheckCircle, ExternalLink, Plug, RefreshCw, Server } from "lucide-react";
import { Link } from "react-router-dom";

import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  LoadingState,
  StatusBadge,
} from "../../../components/ui";
import { connectorApiService } from "../../../services/connectors";
import type { AgentMCPConnection, MCPConnection } from "../../../types/connectors";
import { useAgentDetailContext } from "./types";

export function AgentMCPToolsPage() {
  const { agent } = useAgentDetailContext();
  const [mcpConnections, setMCPConnections] = useState<MCPConnection[]>([]);
  const [agentConnections, setAgentConnections] = useState<AgentMCPConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [updatingMCPId, setUpdatingMCPId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const enabledById = useMemo(() => {
    return new Map(agentConnections.map((connection) => [connection.mcp_id, connection]));
  }, [agentConnections]);

  const loadMCPConnections = async () => {
    setLoading(true);
    setError(null);
    try {
      const [configured, enabled] = await Promise.all([
        connectorApiService.listMCPConnections(),
        connectorApiService.listAgentMCPConnections(agent.agent_id),
      ]);
      setMCPConnections(configured);
      setAgentConnections(enabled);
    } catch (err) {
      console.error("Error loading agent MCP tools:", err);
      setError("Failed to load MCP tools. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadMCPConnections();
  }, [agent.agent_id]);

  const toggleMCP = async (connection: MCPConnection) => {
    const isEnabled = enabledById.has(connection.mcp_id);
    setUpdatingMCPId(connection.mcp_id);
    setError(null);
    try {
      if (isEnabled) {
        await connectorApiService.deleteAgentMCPConnection(agent.agent_id, connection.mcp_id);
      } else {
        await connectorApiService.updateAgentMCPConnection(agent.agent_id, connection.mcp_id, { enabled: true });
      }
      await loadMCPConnections();
    } catch (err) {
      console.error("Error updating agent MCP tool:", err);
      setError(err instanceof Error ? err.message : "Failed to update MCP tool.");
    } finally {
      setUpdatingMCPId(null);
    }
  };

  if (loading) return <LoadingState />;

  return (
    <Card>
      <CardHeader>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", alignItems: "center" }}>
          <div>
            <CardTitle className="text-lg">MCP Tools</CardTitle>
            <CardDescription>
              Enable configured MCP connectors for this agent. The agent can list and call MCP tools at runtime.
            </CardDescription>
          </div>
          <Button size="sm" variant="outline" onClick={() => void loadMCPConnections()}>
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {error && <div style={{ color: "var(--error)", fontSize: "0.875rem", marginBottom: "1rem" }}>{error}</div>}

        {mcpConnections.length === 0 ? (
          <div
            style={{
              display: "grid",
              placeItems: "center",
              gap: "1rem",
              padding: "3rem 1rem",
              textAlign: "center",
            }}
          >
            <IconBox>
              <Server className="h-6 w-6" />
            </IconBox>
            <div>
              <h2 style={{ color: "var(--text-primary)", fontSize: "1.125rem", fontWeight: 600 }}>
                No MCP connectors configured
              </h2>
              <p style={{ color: "var(--text-muted)", marginTop: "0.375rem" }}>
                Add MCP connectors first, then return here to enable them for this agent.
              </p>
            </div>
            <Link to="/dashboard/connectors">
              <Button>
                <Plug className="h-4 w-4" />
                Open connectors
              </Button>
            </Link>
          </div>
        ) : (
          <div style={{ display: "grid", gap: "1rem" }}>
            {mcpConnections.map((connection) => {
              const isAgentEnabled = enabledById.has(connection.mcp_id);
              const disabledByConnector = !connection.enabled;
              return (
                <div
                  key={connection.mcp_id}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    gap: "1rem",
                    alignItems: "center",
                    padding: "1rem",
                    border: "1px solid var(--border-subtle)",
                    borderRadius: "0.75rem",
                    background: "rgba(255,255,255,0.03)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "0.875rem", minWidth: 0 }}>
                    <IconBox size="2.5rem">
                      <Server className="h-5 w-5" />
                    </IconBox>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                        <h3 style={{ color: "var(--text-primary)", fontSize: "1rem", fontWeight: 700 }}>
                          {connection.name}
                        </h3>
                        <StatusBadge
                          status={isAgentEnabled ? "active" : "inactive"}
                          label={isAgentEnabled ? "Enabled for agent" : "Not enabled"}
                        />
                        {disabledByConnector && (
                          <StatusBadge status="inactive" label="Connector disabled" />
                        )}
                      </div>
                      <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", overflowWrap: "anywhere" }}>
                        {connection.server_url}
                      </p>
                      <p style={{ color: "var(--text-muted)", fontSize: "0.8125rem", marginTop: "0.25rem" }}>
                        ID: {connection.mcp_id}
                      </p>
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", justifyContent: "flex-end" }}>
                    <Link to="/dashboard/connectors">
                      <Button variant="outline" size="sm">
                        <ExternalLink className="h-4 w-4" />
                        Configure
                      </Button>
                    </Link>
                    <Button
                      size="sm"
                      variant={isAgentEnabled ? "outline" : "default"}
                      onClick={() => void toggleMCP(connection)}
                      disabled={updatingMCPId === connection.mcp_id || disabledByConnector}
                    >
                      <CheckCircle className="h-4 w-4" />
                      {updatingMCPId === connection.mcp_id
                        ? "Updating..."
                        : isAgentEnabled
                          ? "Disable"
                          : "Enable"}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function IconBox({ children, size = "3rem" }: { children: React.ReactNode; size?: string }) {
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: "0.5rem",
        display: "grid",
        placeItems: "center",
        background: "rgba(255,255,255,0.06)",
        color: "var(--text-primary)",
        flexShrink: 0,
      }}
    >
      {children}
    </div>
  );
}
