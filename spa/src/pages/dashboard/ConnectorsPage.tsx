import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  CheckCircle,
  Edit,
  Globe,
  HardDrive,
  KeyRound,
  Mail,
  Megaphone,
  Plug,
  Plus,
  RefreshCw,
  Server,
  Settings2,
  Trash2,
} from "lucide-react";

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
import type { ConnectorStatus, MCPConnection, MCPProvider, MCPSetupState } from "../../types/connectors";
import { CustomMCPDialog } from "./connectors/CustomMCPDialog";
import { IconBox, ProviderIcon } from "./connectors/connectorUi";
import { returnToConnectors } from "./connectors/connectorUrls";
import { MCPProviderCatalog } from "./connectors/MCPProviderCatalog";
import { MCPRuntimeStatus } from "./connectors/MCPRuntimeStatus";
import { SchemaFormDialog } from "./connectors/SchemaFormDialog";

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

const SETUP_BADGES: Record<MCPSetupState, { status: "active" | "warning" | "info"; label: string }> = {
  ready: { status: "active", label: "Ready" },
  needs_sign_in: { status: "info", label: "Sign in" },
  needs_input: { status: "warning", label: "Needs setup" },
};

function connectorIcon(icon: string) {
  if (icon === "mail") return <Mail className="h-5 w-5" />;
  if (icon === "hard_drive") return <HardDrive className="h-5 w-5" />;
  if (icon === "megaphone") return <Megaphone className="h-5 w-5" />;
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
  const [activeSection, setActiveSection] = useState<ConnectorSection>(() =>
    new URLSearchParams(window.location.search).has("mcp_oauth") ? "mcp" : "google"
  );
  const [connectors, setConnectors] = useState<ConnectorStatus[]>([]);
  const [mcpConnections, setMCPConnections] = useState<MCPConnection[]>([]);
  const [providers, setProviders] = useState<MCPProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [connectingId, setConnectingId] = useState<string | null>(null);
  const [startingMCPOAuthId, setStartingMCPOAuthId] = useState<string | null>(null);
  const [deletingMCPId, setDeletingMCPId] = useState<string | null>(null);
  // null: closed; { editing: null }: creating; { editing }: editing that connection.
  const [customDialog, setCustomDialog] = useState<{ editing: MCPConnection | null } | null>(null);
  const [settingsFor, setSettingsFor] = useState<MCPConnection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mcpError, setMCPError] = useState<string | null>(null);
  const [mcpNotice, setMCPNotice] = useState<string | null>(null);
  // Bumped after a runtime (re)start elsewhere on the page so runtime badges refetch their status.
  const [runtimeVersion, setRuntimeVersion] = useState(0);

  const loadConnectors = async () => {
    setLoading(true);
    setError(null);
    try {
      const [googleData, mcpData, providerData] = await Promise.all([
        connectorApiService.listConnectors(),
        connectorApiService.listMCPConnections(),
        connectorApiService.listMCPProviders(),
      ]);
      setConnectors(googleData);
      setMCPConnections(mcpData);
      setProviders(providerData);
      return mcpData;
    } catch (err) {
      console.error("Error loading connectors:", err);
      setError("Failed to load connectors. Please try again.");
      return [];
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void (async () => {
      const loaded = await loadConnectors();
      await handleOAuthReturn(loaded);
    })();
    // Runs once on mount; the OAuth return parameters are read from the URL a single time.
  }, []);

  const handleOAuthReturn = async (loaded: MCPConnection[]) => {
    const params = new URLSearchParams(window.location.search);
    const outcome = params.get("mcp_oauth");
    if (!outcome) return;
    window.history.replaceState(null, "", window.location.pathname);
    if (outcome !== "success") {
      setMCPError(`Sign-in did not complete: ${params.get("reason") ?? "unknown error"}`);
      return;
    }
    const connection = loaded.find((item) => item.mcp_id === params.get("mcp_id"));
    setMCPNotice(connection ? `${connection.name} is connected.` : "Sign-in complete.");
    // Hosted servers read credentials at start, so start one now with the new sign-in.
    if (connection?.transport === "stdio") {
      await connectorApiService.restartMCPRuntime(connection.mcp_id).catch(() => undefined);
      setRuntimeVersion((version) => version + 1);
    }
  };

  const connectedGoogleCount = useMemo(
    () => connectors.filter((connector) => connector.connected).length,
    [connectors]
  );

  const startConnection = async (connector: ConnectorStatus) => {
    setConnectingId(connector.connector_id);
    setError(null);
    try {
      const response = await connectorApiService.startConnector(connector.connect_path, { return_to: returnToConnectors() });
      window.location.href = response.authorize_url;
    } catch (err) {
      console.error("Error starting connector OAuth:", err);
      setError(`Failed to start ${connector.display_name} connection.`);
      setConnectingId(null);
    }
  };

  const reloadMCP = async () => {
    await loadConnectors();
    setActiveSection("mcp");
  };

  const startMCPOAuth = async (connection: MCPConnection) => {
    setStartingMCPOAuthId(connection.mcp_id);
    setMCPError(null);
    try {
      const response = await connectorApiService.startMCPOAuth(connection.mcp_id, { return_to: returnToConnectors() });
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
      setProviders(await connectorApiService.listMCPProviders());
    } catch (err) {
      console.error("Error deleting MCP connector:", err);
      setMCPError(err instanceof Error ? err.message : "Failed to delete MCP connector.");
    } finally {
      setDeletingMCPId(null);
    }
  };

  const providerFor = (connection: MCPConnection) =>
    providers.find((provider) => provider.key === connection.provider_key) ?? null;

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
          <Button onClick={() => setCustomDialog({ editing: null })}>
            <Plus className="h-4 w-4" />
            Custom MCP
          </Button>
        </div>
      </div>

      {error && <div style={{ color: "var(--error)", fontSize: "0.875rem" }}>{error}</div>}
      {mcpError && <div style={{ color: "var(--error)", fontSize: "0.875rem" }}>{mcpError}</div>}
      {mcpNotice && <div style={{ color: "var(--success, var(--text-primary))", fontSize: "0.875rem" }}>{mcpNotice}</div>}

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
            <div style={{ display: "grid", gap: "2rem" }}>
              <section>
                <SectionHeader
                  icon={<Plug className="h-5 w-5" />}
                  title="MCP providers"
                  description="Ready-made connectors configured by InnoMight Labs. Install one and supply only your own credentials."
                />
                <MCPProviderCatalog providers={providers} onInstalled={reloadMCP} onError={setMCPError} />
              </section>

              <section>
                <SectionHeader
                  icon={<Server className="h-5 w-5" />}
                  title="Your MCP connectors"
                  description="Installed providers and custom servers. Enable them per agent from the agent settings."
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
                            Install a provider above, or add a custom remote or hosted MCP server.
                          </p>
                        </div>
                        <Button onClick={() => setCustomDialog({ editing: null })}>
                          <Plus className="h-4 w-4" />
                          Add custom MCP server
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                ) : (
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(22rem, 1fr))", gap: "1rem" }}>
                    {mcpConnections.map((connection) => (
                      <MCPConnectionCard
                        key={`${connection.mcp_id}-${runtimeVersion}`}
                        connection={connection}
                        provider={providerFor(connection)}
                        signingIn={startingMCPOAuthId === connection.mcp_id}
                        deleting={deletingMCPId === connection.mcp_id}
                        onSignIn={() => void startMCPOAuth(connection)}
                        onEdit={() =>
                          connection.provider_key ? setSettingsFor(connection) : setCustomDialog({ editing: connection })
                        }
                        onDelete={() => void deleteMCPConnection(connection)}
                      />
                    ))}
                  </div>
                )}
              </section>
            </div>
          )}
        </main>
      </div>

      {customDialog && (
        <CustomMCPDialog
          key={customDialog.editing?.mcp_id ?? "new"}
          editing={customDialog.editing}
          onClose={() => setCustomDialog(null)}
          onSaved={async () => {
            setCustomDialog(null);
            await reloadMCP();
          }}
        />
      )}

      {settingsFor && (
        <SchemaFormDialog
          key={settingsFor.mcp_id}
          title={`${settingsFor.name} settings`}
          description="Secret fields are blank; leave them blank to keep the stored values."
          submitLabel="Save settings"
          loadSchema={() => connectorApiService.getMCPConnectionSettingsForm(settingsFor.mcp_id)}
          onSubmit={async (inputs) => {
            await connectorApiService.updateMCPConnection(settingsFor.mcp_id, { inputs });
            setSettingsFor(null);
            await reloadMCP();
          }}
          onClose={() => setSettingsFor(null)}
        />
      )}
    </div>
  );
}

function MCPConnectionCard({
  connection,
  provider,
  signingIn,
  deleting,
  onSignIn,
  onEdit,
  onDelete,
}: {
  connection: MCPConnection;
  provider: MCPProvider | null;
  signingIn: boolean;
  deleting: boolean;
  onSignIn: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const isStdio = connection.transport === "stdio";
  const setup = connection.provider_key ? SETUP_BADGES[connection.setup_state] : null;
  const description = provider
    ? provider.display_name
    : isStdio && connection.stdio
      ? [connection.stdio.package, ...connection.stdio.args].join(" ")
      : connection.server_url;
  const authLabel = { none: "None", api_key: isStdio ? "Environment" : "API key", oauth: "OAuth" }[connection.auth_type];

  return (
    <Card>
      <CardHeader>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", alignItems: "flex-start" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", minWidth: 0 }}>
            <IconBox>{provider ? <ProviderIcon icon={provider.icon} /> : <Server className="h-5 w-5" />}</IconBox>
            <div style={{ minWidth: 0 }}>
              <CardTitle>{connection.name}</CardTitle>
              <CardDescription style={{ overflowWrap: "anywhere" }}>{description}</CardDescription>
            </div>
          </div>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", justifyContent: "flex-end" }}>
            {setup && <StatusBadge status={setup.status} label={setup.label} />}
            <StatusBadge status={connection.enabled ? "active" : "inactive"} label={connection.enabled ? "Enabled" : "Disabled"} />
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div style={{ display: "grid", gap: "0.5rem", color: "var(--text-muted)", fontSize: "0.875rem" }}>
            <span>ID: {connection.mcp_id}</span>
            <span>Transport: {isStdio ? "Hosted (stdio)" : "Streamable HTTP"}</span>
            <span>
              Auth: {authLabel}
              {connection.auth_type === "oauth" ? (connection.oauth_connected ? " connected" : " not connected") : ""}
            </span>
            <span>Created: {formatDate(connection.created_at)}</span>
          </div>
          {isStdio && (
            <MCPRuntimeStatus
              mcpId={connection.mcp_id}
              canStart={connection.enabled && connection.setup_state === "ready" && (connection.auth_type !== "oauth" || connection.oauth_connected)}
            />
          )}
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
            {connection.auth_type === "oauth" && (
              <Button variant={connection.oauth_connected ? "outline" : "default"} onClick={onSignIn} disabled={signingIn}>
                <KeyRound className="h-4 w-4" />
                {signingIn ? "Opening..." : connection.oauth_connected ? "Sign in again" : "Sign in"}
              </Button>
            )}
            <Button variant="outline" onClick={onEdit}>
              {connection.provider_key ? <Settings2 className="h-4 w-4" /> : <Edit className="h-4 w-4" />}
              {connection.provider_key ? "Settings" : "Edit"}
            </Button>
            <Button variant="outline" onClick={onDelete} disabled={deleting}>
              <Trash2 className="h-4 w-4" />
              {deleting ? "Deleting..." : connection.provider_key ? "Uninstall" : "Delete"}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
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
            <Button
              key={item.id}
              type="button"
              variant="ghost"
              onClick={() => onChange(item.id)}
              className={
                isActive
                  ? "text-[var(--nav-active-text)]"
                  : "text-[var(--text-muted)] hover:bg-[var(--nav-hover-bg)] hover:text-[var(--text-primary)]"
              }
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "flex-start",
                gap: "0.75rem",
                borderRadius: "0.75rem",
                height: "auto",
                padding: "0.75rem",
                fontSize: "0.875rem",
                fontWeight: 500,
                textAlign: "left",
                width: "100%",
                transition: "all 0.2s",
                background: isActive
                  ? "var(--nav-active-bg)"
                  : undefined,
              }}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              {item.label}
            </Button>
          );
        })}
      </nav>
    </aside>
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
