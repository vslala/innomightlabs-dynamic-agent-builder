import { useEffect, useState } from "react";
import { CheckCircle, HardDrive, Mail, Plug, RefreshCw } from "lucide-react";

import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  ErrorState,
  LoadingState,
  StatusBadge,
} from "../../components/ui";
import { connectorApiService } from "../../services/connectors";
import type { ConnectorStatus } from "../../types/connectors";

function connectorIcon(icon: string) {
  if (icon === "mail") return <Mail className="h-5 w-5" />;
  if (icon === "hard_drive") return <HardDrive className="h-5 w-5" />;
  return <Plug className="h-5 w-5" />;
}

export function ConnectorsPage() {
  const [connectors, setConnectors] = useState<ConnectorStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [connectingId, setConnectingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadConnectors = async () => {
    setLoading(true);
    setError(null);
    try {
      setConnectors(await connectorApiService.listConnectors());
    } catch (err) {
      console.error("Error loading connectors:", err);
      setError("Failed to load connectors. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadConnectors();
  }, []);

  const startConnection = async (connector: ConnectorStatus) => {
    setConnectingId(connector.connector_id);
    setError(null);
    try {
      const returnTo = `${window.location.origin}/dashboard/connectors`;
      const response = await connectorApiService.startConnector(connector.connect_path, { return_to: returnTo });
      window.location.href = response.authorize_url;
    } catch (err) {
      console.error("Error starting connector OAuth:", err);
      setError(`Failed to start ${connector.display_name} connection.`);
      setConnectingId(null);
    }
  };

  if (loading) return <LoadingState />;
  if (error && connectors.length === 0) return <ErrorState message={error} onRetry={loadConnectors} />;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", alignItems: "center" }}>
        <div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", marginBottom: "0.25rem" }}>
            Account Connections
          </p>
          <h1 style={{ color: "var(--text-primary)", fontSize: "2rem", fontWeight: 700 }}>Connectors</h1>
        </div>
        <Button variant="outline" onClick={() => void loadConnectors()}>
          <RefreshCw className="h-4 w-4" />
          Refresh
        </Button>
      </div>

      {error && <div style={{ color: "var(--error)", fontSize: "0.875rem" }}>{error}</div>}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(18rem, 1fr))", gap: "1rem" }}>
        {connectors.map((connector) => (
          <Card key={connector.connector_id}>
            <CardHeader>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", alignItems: "center" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                  <div
                    style={{
                      width: "2.5rem",
                      height: "2.5rem",
                      borderRadius: "0.5rem",
                      display: "grid",
                      placeItems: "center",
                      background: "rgba(255,255,255,0.06)",
                      color: "var(--text-primary)",
                    }}
                  >
                    {connectorIcon(connector.icon)}
                  </div>
                  <div>
                    <CardTitle>{connector.display_name}</CardTitle>
                    <CardDescription>{connector.provider_name}</CardDescription>
                  </div>
                </div>
                <StatusBadge
                  status={connector.connected ? "active" : "inactive"}
                  label={connector.connected ? "Connected" : "Not connected"}
                />
              </div>
            </CardHeader>
            <CardContent>
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", lineHeight: 1.6 }}>
                  {connector.connected
                    ? "This account can be used by enabled skills in agents and automations."
                    : "Connect this account to make dependent skills available in agents and automations."}
                </p>
                <Button
                  onClick={() => void startConnection(connector)}
                  disabled={connectingId === connector.connector_id}
                  variant={connector.connected ? "outline" : "default"}
                >
                  {connector.connected ? <RefreshCw className="h-4 w-4" /> : <CheckCircle className="h-4 w-4" />}
                  {connectingId === connector.connector_id
                    ? "Opening..."
                    : connector.connected
                      ? "Reconnect"
                      : "Connect"}
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
