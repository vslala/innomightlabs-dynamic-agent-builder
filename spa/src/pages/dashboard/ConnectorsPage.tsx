import { useEffect, useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  CheckCircle,
  Edit,
  Globe,
  HardDrive,
  KeyRound,
  Mail,
  Minus,
  Plug,
  Plus,
  RefreshCw,
  Server,
  Trash2,
} from "lucide-react";

import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  ErrorState,
  Input,
  Label,
  LoadingState,
  StatusBadge,
} from "../../components/ui";
import { connectorApiService } from "../../services/connectors";
import type { ConnectorStatus, MCPConnection } from "../../types/connectors";
import type { MCPAuthType } from "../../types/connectors";

type ConnectorSection = "google" | "mcp";

interface ConnectorNavItem {
  id: ConnectorSection;
  label: string;
  icon: typeof Globe;
}

const connectorNavItems: ConnectorNavItem[] = [
  { id: "google", label: "Google", icon: Globe },
  { id: "mcp", label: "MCP", icon: Server },
];

interface MCPFormState {
  name: string;
  serverUrl: string;
  authType: MCPAuthType;
  headers: MCPHeaderRow[];
  authorizationUrl: string;
  tokenUrl: string;
  clientId: string;
  clientSecret: string;
  scope: string;
  resourceUrl: string;
  enabled: boolean;
}

interface MCPHeaderRow {
  id: string;
  name: string;
  value: string;
}

const emptyMCPForm: MCPFormState = {
  name: "",
  serverUrl: "",
  authType: "api_key",
  headers: [{ id: "header-1", name: "Authorization", value: "" }],
  authorizationUrl: "",
  tokenUrl: "",
  clientId: "",
  clientSecret: "",
  scope: "",
  resourceUrl: "",
  enabled: true,
};

function connectorIcon(icon: string) {
  if (icon === "mail") return <Mail className="h-5 w-5" />;
  if (icon === "hard_drive") return <HardDrive className="h-5 w-5" />;
  return <Plug className="h-5 w-5" />;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function ConnectorsPage() {
  const [activeSection, setActiveSection] = useState<ConnectorSection>("google");
  const [connectors, setConnectors] = useState<ConnectorStatus[]>([]);
  const [mcpConnections, setMCPConnections] = useState<MCPConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [connectingId, setConnectingId] = useState<string | null>(null);
  const [savingMCP, setSavingMCP] = useState(false);
  const [fetchingMCPOAuthDetails, setFetchingMCPOAuthDetails] = useState(false);
  const [startingMCPOAuthId, setStartingMCPOAuthId] = useState<string | null>(null);
  const [deletingMCPId, setDeletingMCPId] = useState<string | null>(null);
  const [editingMCP, setEditingMCP] = useState<MCPConnection | null>(null);
  const [mcpDialogOpen, setMCPDialogOpen] = useState(false);
  const [mcpForm, setMCPForm] = useState<MCPFormState>(emptyMCPForm);
  const [error, setError] = useState<string | null>(null);
  const [mcpError, setMCPError] = useState<string | null>(null);

  const loadConnectors = async () => {
    setLoading(true);
    setError(null);
    try {
      const [googleData, mcpData] = await Promise.all([
        connectorApiService.listConnectors(),
        connectorApiService.listMCPConnections(),
      ]);
      setConnectors(googleData);
      setMCPConnections(mcpData);
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

  const connectedGoogleCount = useMemo(
    () => connectors.filter((connector) => connector.connected).length,
    [connectors]
  );

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

  const openCreateMCPDialog = () => {
    setEditingMCP(null);
    setMCPForm(emptyMCPForm);
    setMCPError(null);
    setMCPDialogOpen(true);
  };

  const openEditMCPDialog = (connection: MCPConnection) => {
    setEditingMCP(connection);
    setMCPForm({
      name: connection.name,
      serverUrl: connection.server_url,
      authType: connection.auth_type,
      headers: [{ id: "header-1", name: "Authorization", value: "" }],
      authorizationUrl: "",
      tokenUrl: "",
      clientId: "",
      clientSecret: "",
      scope: "",
      resourceUrl: "",
      enabled: connection.enabled,
    });
    setMCPError(null);
    setMCPDialogOpen(true);
  };

  const closeMCPDialog = () => {
    if (savingMCP) return;
    setMCPDialogOpen(false);
    setEditingMCP(null);
    setMCPForm(emptyMCPForm);
    setMCPError(null);
  };

  const handleMCPSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSavingMCP(true);
    setMCPError(null);
    try {
      const name = mcpForm.name.trim();
      const serverUrl = mcpForm.serverUrl.trim();
      const authHeaderRows = mcpForm.headers
        .map((header) => ({ name: header.name.trim(), value: header.value.trim() }))
        .filter((header) => header.name || header.value);
      const shouldUpdateHeaders = !editingMCP || authHeaderRows.some((header) => header.value);
      const oauthConfig = {
        authorization_url: mcpForm.authorizationUrl.trim(),
        token_url: mcpForm.tokenUrl.trim(),
        client_id: mcpForm.clientId.trim(),
        client_secret: mcpForm.clientSecret.trim(),
        scope: mcpForm.scope.trim(),
        resource_url: mcpForm.resourceUrl.trim(),
      };
      const shouldUpdateOAuth =
        !editingMCP ||
        editingMCP.auth_type !== "oauth" ||
        Boolean(
          oauthConfig.authorization_url ||
            oauthConfig.token_url ||
            oauthConfig.client_id ||
            oauthConfig.client_secret ||
            oauthConfig.scope ||
            oauthConfig.resource_url
        );

      if (!name || !serverUrl) {
        setMCPError("Name and server URL are required.");
        return;
      }
      if (mcpForm.authType === "api_key") {
        if (shouldUpdateHeaders && authHeaderRows.some((header) => !header.name || !header.value)) {
          setMCPError("Each auth header must include both key and value.");
          return;
        }
        if (shouldUpdateHeaders && authHeaderRows.length === 0) {
          setMCPError("At least one auth header is required for a new MCP connector.");
          return;
        }
      }
      if (mcpForm.authType === "oauth" && shouldUpdateOAuth) {
        if (!oauthConfig.authorization_url || !oauthConfig.token_url || !oauthConfig.client_id) {
          setMCPError("Authorization URL, token URL, and client ID are required for OAuth MCP connectors.");
          return;
        }
      }

      if (editingMCP) {
        await connectorApiService.updateMCPConnection(editingMCP.mcp_id, {
          name,
          server_url: serverUrl,
          enabled: mcpForm.enabled,
          ...(mcpForm.authType === "api_key" && shouldUpdateHeaders
            ? {
                auth_type: "api_key",
                api_key: { headers: authHeaderRows },
              }
            : {}),
          ...(mcpForm.authType === "oauth" && shouldUpdateOAuth
            ? {
                auth_type: "oauth",
                oauth: oauthConfig,
              }
            : {}),
        });
      } else {
        await connectorApiService.createMCPConnection({
          name,
          server_url: serverUrl,
          auth_type: mcpForm.authType,
          enabled: mcpForm.enabled,
          ...(mcpForm.authType === "api_key"
            ? { api_key: { headers: authHeaderRows } }
            : { oauth: oauthConfig }),
        });
      }

      closeMCPDialog();
      await loadConnectors();
      setActiveSection("mcp");
    } catch (err) {
      console.error("Error saving MCP connector:", err);
      setMCPError(err instanceof Error ? err.message : "Failed to save MCP connector.");
    } finally {
      setSavingMCP(false);
    }
  };

  const fetchMCPOAuthDetails = async () => {
    const serverUrl = mcpForm.serverUrl.trim();
    if (!serverUrl) {
      setMCPError("Enter the MCP server URL before fetching OAuth details.");
      return;
    }

    setFetchingMCPOAuthDetails(true);
    setMCPError(null);
    try {
      const details = await connectorApiService.discoverMCPOAuth({ server_url: serverUrl });
      setMCPForm((current) => ({
        ...current,
        authType: "oauth",
        authorizationUrl: details.authorization_url,
        tokenUrl: details.token_url,
        clientId: details.client_id,
        clientSecret: details.client_secret,
        scope: details.scope,
        resourceUrl: details.resource_url,
      }));
      if (!details.client_id) {
        setMCPError("OAuth endpoints were found. This server did not auto-register a client, so enter the client ID manually.");
      }
    } catch (err) {
      console.error("Error fetching MCP OAuth details:", err);
      setMCPError(err instanceof Error ? err.message : "Failed to fetch MCP OAuth details.");
    } finally {
      setFetchingMCPOAuthDetails(false);
    }
  };

  const startMCPOAuth = async (connection: MCPConnection) => {
    setStartingMCPOAuthId(connection.mcp_id);
    setMCPError(null);
    try {
      const returnTo = `${window.location.origin}/dashboard/connectors`;
      const response = await connectorApiService.startMCPOAuth(connection.mcp_id, { return_to: returnTo });
      window.location.href = response.authorize_url;
    } catch (err) {
      console.error("Error starting MCP OAuth:", err);
      setMCPError(err instanceof Error ? err.message : "Failed to start MCP OAuth.");
      setStartingMCPOAuthId(null);
    }
  };

  const deleteMCPConnection = async (connection: MCPConnection) => {
    const confirmed = window.confirm(`Delete MCP connector "${connection.name}"?`);
    if (!confirmed) return;

    setDeletingMCPId(connection.mcp_id);
    setMCPError(null);
    try {
      await connectorApiService.deleteMCPConnection(connection.mcp_id);
      setMCPConnections((current) => current.filter((item) => item.mcp_id !== connection.mcp_id));
    } catch (err) {
      console.error("Error deleting MCP connector:", err);
      setMCPError(err instanceof Error ? err.message : "Failed to delete MCP connector.");
    } finally {
      setDeletingMCPId(null);
    }
  };

  if (loading) return <LoadingState />;
  if (error && connectors.length === 0 && mcpConnections.length === 0) {
    return <ErrorState message={error} onRetry={loadConnectors} />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", alignItems: "center" }}>
        <div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", marginBottom: "0.25rem" }}>
            Account Connections
          </p>
          <h1 style={{ color: "var(--text-primary)", fontSize: "2rem", fontWeight: 700 }}>Connectors</h1>
        </div>
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
          <Button variant="outline" onClick={() => void loadConnectors()}>
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
          <Button onClick={openCreateMCPDialog}>
            <Plus className="h-4 w-4" />
            Add MCP
          </Button>
        </div>
      </div>

      {error && <div style={{ color: "var(--error)", fontSize: "0.875rem" }}>{error}</div>}
      {mcpError && <div style={{ color: "var(--error)", fontSize: "0.875rem" }}>{mcpError}</div>}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "15rem minmax(0, 1fr)",
          gap: "1.5rem",
          alignItems: "start",
        }}
      >
        <ConnectorSideNav activeSection={activeSection} onChange={setActiveSection} />

        <main style={{ minWidth: 0 }}>
          {activeSection === "google" ? (
            <>
              <SectionHeader
                icon={<Globe className="h-5 w-5" />}
                title="Google connectors"
                description={`${connectedGoogleCount}/${connectors.length} accounts connected for Google-backed skills.`}
              />
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(18rem, 1fr))", gap: "1rem" }}>
                {connectors.map((connector) => (
                  <Card key={connector.connector_id}>
                    <CardHeader>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", alignItems: "center" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                          <IconBox>{connectorIcon(connector.icon)}</IconBox>
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
            </>
          ) : (
            <>
              <SectionHeader
                icon={<Server className="h-5 w-5" />}
                title="MCP connectors"
                description="Configure Streamable HTTP MCP servers here, then enable them per agent from the agent settings."
              />
              {mcpConnections.length === 0 ? (
                <Card>
                  <CardContent style={{ padding: "3rem", textAlign: "center" }}>
                    <div style={{ display: "grid", placeItems: "center", gap: "1rem" }}>
                      <IconBox size="3rem">
                        <Server className="h-6 w-6" />
                      </IconBox>
                      <div>
                        <h2 style={{ color: "var(--text-primary)", fontSize: "1.125rem", fontWeight: 600 }}>
                          No MCP connectors yet
                        </h2>
                        <p style={{ color: "var(--text-muted)", marginTop: "0.375rem" }}>
                          Add a Streamable HTTP MCP endpoint to make its tools available to your agents.
                        </p>
                      </div>
                      <Button onClick={openCreateMCPDialog}>
                        <Plus className="h-4 w-4" />
                        Add MCP connector
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ) : (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(22rem, 1fr))", gap: "1rem" }}>
                  {mcpConnections.map((connection) => (
                    <Card key={connection.mcp_id}>
                      <CardHeader>
                        <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", alignItems: "flex-start" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", minWidth: 0 }}>
                            <IconBox>
                              <Server className="h-5 w-5" />
                            </IconBox>
                            <div style={{ minWidth: 0 }}>
                              <CardTitle>{connection.name}</CardTitle>
                              <CardDescription style={{ overflowWrap: "anywhere" }}>{connection.server_url}</CardDescription>
                            </div>
                          </div>
                          <StatusBadge
                            status={connection.enabled ? "active" : "inactive"}
                            label={connection.enabled ? "Enabled" : "Disabled"}
                          />
                        </div>
                      </CardHeader>
                      <CardContent>
                        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                          <div style={{ display: "grid", gap: "0.5rem", color: "var(--text-muted)", fontSize: "0.875rem" }}>
                            <span>ID: {connection.mcp_id}</span>
                            <span>Transport: Streamable HTTP</span>
                            <span>
                              Auth: {connection.auth_type === "oauth" ? "OAuth" : "API key"}
                              {connection.auth_type === "oauth"
                                ? connection.oauth_connected
                                  ? " connected"
                                  : " not connected"
                                : ""}
                            </span>
                            <span>Created: {formatDate(connection.created_at)}</span>
                          </div>
                          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
                            {connection.auth_type === "oauth" && (
                              <Button
                                variant={connection.oauth_connected ? "outline" : "default"}
                                onClick={() => void startMCPOAuth(connection)}
                                disabled={startingMCPOAuthId === connection.mcp_id}
                              >
                                <KeyRound className="h-4 w-4" />
                                {startingMCPOAuthId === connection.mcp_id
                                  ? "Opening..."
                                  : connection.oauth_connected
                                    ? "Reconnect OAuth"
                                    : "Connect OAuth"}
                              </Button>
                            )}
                            <Button variant="outline" onClick={() => openEditMCPDialog(connection)}>
                              <Edit className="h-4 w-4" />
                              Edit
                            </Button>
                            <Button
                              variant="outline"
                              onClick={() => void deleteMCPConnection(connection)}
                              disabled={deletingMCPId === connection.mcp_id}
                            >
                              <Trash2 className="h-4 w-4" />
                              {deletingMCPId === connection.mcp_id ? "Deleting..." : "Delete"}
                            </Button>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </>
          )}
        </main>
      </div>

      <Dialog open={mcpDialogOpen} onOpenChange={(open) => (open ? setMCPDialogOpen(true) : closeMCPDialog())}>
        <DialogContent style={{ maxWidth: "36rem" }}>
          <DialogHeader>
            <DialogTitle>{editingMCP ? "Edit MCP connector" : "Add MCP connector"}</DialogTitle>
            <DialogDescription>
              Configure a Streamable HTTP MCP server with API-key or OAuth authentication.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={(event) => void handleMCPSubmit(event)} style={{ display: "grid", gap: "1rem" }}>
            <Field label="Name" htmlFor="mcp-name">
              <Input
                id="mcp-name"
                value={mcpForm.name}
                placeholder="Ahrefs SEO"
                onChange={(event) => setMCPForm((current) => ({ ...current, name: event.target.value }))}
                required
              />
            </Field>
            <Field label="Server URL" htmlFor="mcp-server-url">
              <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: "0.75rem" }}>
                <Input
                  id="mcp-server-url"
                  value={mcpForm.serverUrl}
                  placeholder="https://example.com/mcp"
                  onChange={(event) => setMCPForm((current) => ({ ...current, serverUrl: event.target.value }))}
                  required
                />
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => void fetchMCPOAuthDetails()}
                  disabled={fetchingMCPOAuthDetails || !mcpForm.serverUrl.trim()}
                >
                  <RefreshCw className="h-4 w-4" />
                  {fetchingMCPOAuthDetails ? "Fetching..." : "Fetch auth"}
                </Button>
              </div>
            </Field>
            <div style={{ display: "grid", gap: "0.75rem" }}>
              <Label>Authentication</Label>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                <Button
                  type="button"
                  variant={mcpForm.authType === "api_key" ? "default" : "outline"}
                  onClick={() => setMCPForm((current) => ({ ...current, authType: "api_key" }))}
                >
                  <KeyRound className="h-4 w-4" />
                  API key
                </Button>
                <Button
                  type="button"
                  variant={mcpForm.authType === "oauth" ? "default" : "outline"}
                  onClick={() => setMCPForm((current) => ({ ...current, authType: "oauth" }))}
                >
                  <Globe className="h-4 w-4" />
                  OAuth
                </Button>
              </div>
            </div>
            {mcpForm.authType === "api_key" ? (
              <div style={{ display: "grid", gap: "0.75rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", alignItems: "center" }}>
                <Label>Auth headers</Label>
                <Button type="button" variant="outline" size="sm" onClick={() => setMCPForm(addHeaderRow)}>
                  <Plus className="h-4 w-4" />
                  Add header
                </Button>
              </div>
              {mcpForm.headers.map((header, index) => (
                <div
                  key={header.id}
                  style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1.4fr) auto", gap: "0.75rem" }}
                >
                  <Input
                    value={header.name}
                    placeholder="Authorization"
                    aria-label={`Header ${index + 1} key`}
                    onChange={(event) => setMCPForm((current) => updateHeaderRow(current, header.id, "name", event.target.value))}
                  />
                  <Input
                    type="password"
                    value={header.value}
                    placeholder={editingMCP ? "Leave blank to keep existing headers" : "Bearer ..."}
                    aria-label={`Header ${index + 1} value`}
                    onChange={(event) => setMCPForm((current) => updateHeaderRow(current, header.id, "value", event.target.value))}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    onClick={() => setMCPForm((current) => removeHeaderRow(current, header.id))}
                    disabled={mcpForm.headers.length === 1}
                    aria-label={`Remove header ${index + 1}`}
                  >
                    <Minus className="h-4 w-4" />
                  </Button>
                </div>
              ))}
              {editingMCP && (
                <p style={{ color: "var(--text-muted)", fontSize: "0.8125rem" }}>
                  Leave all header values blank to keep the current stored headers.
                </p>
              )}
            </div>
            ) : (
              <div style={{ display: "grid", gap: "0.875rem" }}>
                <Field label="Authorization URL" htmlFor="mcp-oauth-authorization-url">
                  <Input
                    id="mcp-oauth-authorization-url"
                    value={mcpForm.authorizationUrl}
                    placeholder={editingMCP ? "Leave blank to keep existing URL" : "https://provider.example/oauth/authorize"}
                    onChange={(event) => setMCPForm((current) => ({ ...current, authorizationUrl: event.target.value }))}
                    required={!editingMCP || editingMCP.auth_type !== "oauth"}
                  />
                </Field>
                <Field label="Token URL" htmlFor="mcp-oauth-token-url">
                  <Input
                    id="mcp-oauth-token-url"
                    value={mcpForm.tokenUrl}
                    placeholder={editingMCP ? "Leave blank to keep existing URL" : "https://provider.example/oauth/token"}
                    onChange={(event) => setMCPForm((current) => ({ ...current, tokenUrl: event.target.value }))}
                    required={!editingMCP || editingMCP.auth_type !== "oauth"}
                  />
                </Field>
                <Field label="Client ID" htmlFor="mcp-oauth-client-id">
                  <Input
                    id="mcp-oauth-client-id"
                    value={mcpForm.clientId}
                    placeholder={editingMCP ? "Leave blank to keep existing client ID" : "OAuth client ID"}
                    onChange={(event) => setMCPForm((current) => ({ ...current, clientId: event.target.value }))}
                    required={!editingMCP || editingMCP.auth_type !== "oauth"}
                  />
                </Field>
                <Field label="Client secret" htmlFor="mcp-oauth-client-secret">
                  <Input
                    id="mcp-oauth-client-secret"
                    type="password"
                    value={mcpForm.clientSecret}
                    placeholder={editingMCP ? "Leave blank to keep existing client secret" : "Optional OAuth client secret"}
                    onChange={(event) => setMCPForm((current) => ({ ...current, clientSecret: event.target.value }))}
                  />
                </Field>
                <Field label="Scopes" htmlFor="mcp-oauth-scope">
                  <Input
                    id="mcp-oauth-scope"
                    value={mcpForm.scope}
                    placeholder="read write"
                    onChange={(event) => setMCPForm((current) => ({ ...current, scope: event.target.value }))}
                  />
                </Field>
                <Field label="Resource URL" htmlFor="mcp-oauth-resource-url">
                  <Input
                    id="mcp-oauth-resource-url"
                    value={mcpForm.resourceUrl}
                    placeholder="Defaults to the canonical MCP server URL"
                    onChange={(event) => setMCPForm((current) => ({ ...current, resourceUrl: event.target.value }))}
                  />
                </Field>
                {editingMCP && editingMCP.auth_type === "oauth" && (
                  <p style={{ color: "var(--text-muted)", fontSize: "0.8125rem" }}>
                    Leave OAuth fields blank to keep the current stored provider config.
                  </p>
                )}
              </div>
            )}
            <label
              style={{
                display: "flex",
                gap: "0.75rem",
                alignItems: "center",
                padding: "0.875rem",
                border: "1px solid var(--border-subtle)",
                borderRadius: "0.5rem",
                background: "rgba(255,255,255,0.03)",
              }}
            >
              <input
                type="checkbox"
                checked={mcpForm.enabled}
                onChange={(event) => setMCPForm((current) => ({ ...current, enabled: event.target.checked }))}
              />
              <span style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>Enabled</span>
                <span style={{ color: "var(--text-muted)", fontSize: "0.8125rem" }}>
                  Disabled MCPs stay configured but cannot be enabled by agents.
                </span>
              </span>
            </label>
            {mcpError && <div style={{ color: "var(--error)", fontSize: "0.875rem" }}>{mcpError}</div>}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={closeMCPDialog} disabled={savingMCP}>
                Cancel
              </Button>
              <Button type="submit" disabled={savingMCP}>
                <KeyRound className="h-4 w-4" />
                {savingMCP ? "Saving..." : editingMCP ? "Save connector" : "Create connector"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function addHeaderRow(current: MCPFormState): MCPFormState {
  return {
    ...current,
    headers: [
      ...current.headers,
      { id: `header-${Date.now()}-${current.headers.length}`, name: "", value: "" },
    ],
  };
}

function updateHeaderRow(
  current: MCPFormState,
  id: string,
  field: "name" | "value",
  value: string
): MCPFormState {
  return {
    ...current,
    headers: current.headers.map((header) =>
      header.id === id ? { ...header, [field]: value } : header
    ),
  };
}

function removeHeaderRow(current: MCPFormState, id: string): MCPFormState {
  if (current.headers.length <= 1) return current;
  return {
    ...current,
    headers: current.headers.filter((header) => header.id !== id),
  };
}

function ConnectorSideNav({
  activeSection,
  onChange,
}: {
  activeSection: ConnectorSection;
  onChange: (section: ConnectorSection) => void;
}) {
  return (
    <aside
      style={{
        width: "15rem",
        minWidth: "15rem",
        borderRight: "1px solid var(--border-subtle)",
        paddingRight: "1rem",
      }}
    >
      <nav style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
        {connectorNavItems.map((item) => {
          const isActive = activeSection === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onChange(item.id)}
              className={
                isActive
                  ? "bg-gradient-to-r from-[var(--gradient-start)]/15 to-[var(--gradient-mid)]/15 text-white"
                  : "text-[var(--text-muted)] hover:bg-white/5 hover:text-[var(--text-primary)]"
              }
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.75rem",
                borderRadius: "0.75rem",
                padding: "0.75rem",
                fontSize: "0.875rem",
                fontWeight: 500,
                border: 0,
                cursor: "pointer",
                textAlign: "left",
                width: "100%",
                transition: "all 0.2s",
              }}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              {item.label}
            </button>
          );
        })}
      </nav>
    </aside>
  );
}

function IconBox({ children, size = "2.5rem" }: { children: ReactNode; size?: string }) {
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

function SectionHeader({
  icon,
  title,
  description,
}: {
  icon: ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1rem" }}>
      <IconBox>{icon}</IconBox>
      <div>
        <h2 style={{ color: "var(--text-primary)", fontSize: "1.125rem", fontWeight: 700 }}>{title}</h2>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", marginTop: "0.25rem" }}>{description}</p>
      </div>
    </div>
  );
}

function Field({ label, htmlFor, children }: { label: string; htmlFor: string; children: ReactNode }) {
  return (
    <div style={{ display: "grid", gap: "0.5rem" }}>
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
    </div>
  );
}
