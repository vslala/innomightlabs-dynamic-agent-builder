import { useEffect, useMemo, useState } from "react";
import { CheckCircle, RefreshCw } from "lucide-react";

import { Button, ErrorState, LoadingState, Tabs, TabsContent, TabsList, TabsTrigger } from "../../components/ui";
import { useCanManageSettings } from "../../hooks/useCanManageSettings";
import { connectorApiService } from "../../services/connectors";
import type { ConnectorStatus, MCPConnection, MCPProvider } from "../../types/connectors";
import { buildCatalog, type CatalogItem } from "./connectors/catalogItems";
import { ConnectorCatalog } from "./connectors/ConnectorCatalog";
import styles from "./connectors/ConnectorCatalog.module.css";
import { ConnectorDetailsDialog } from "./connectors/ConnectorDetailsDialog";
import { CustomMCPDialog } from "./connectors/CustomMCPDialog";
import { connectorsTabFromSearch, returnToConnectors, type ConnectorsTab } from "./connectors/connectorUrls";
import { connectionIcon } from "./connectors/connectionIcon";
import { SchemaFormDialog } from "./connectors/SchemaFormDialog";
import { SocialAccountsTab } from "./connectors/social/SocialAccountsTab";

/** What the details dialog is open on: a catalog item, or one hand-added server. */
type DetailsTarget = { kind: "item"; key: string } | { kind: "custom"; mcpId: string };

export function ConnectorsPage() {
  const [connectors, setConnectors] = useState<ConnectorStatus[]>([]);
  const [mcpConnections, setMCPConnections] = useState<MCPConnection[]>([]);
  const [providers, setProviders] = useState<MCPProvider[]>([]);
  const [loading, setLoading] = useState(true);
  // MCPs (and the Google accounts) or social accounts; `?tab=social` is where social sign-ins return
  const [tab, setTab] = useState<ConnectorsTab>(() => connectorsTabFromSearch(window.location.search));
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [startingMCPOAuthId, setStartingMCPOAuthId] = useState<string | null>(null);
  const [deletingMCPId, setDeletingMCPId] = useState<string | null>(null);
  const [details, setDetails] = useState<DetailsTarget | null>(null);
  // null: closed; { editing: null }: creating; { editing }: editing that connection.
  const [customDialog, setCustomDialog] = useState<{ editing: MCPConnection | null } | null>(null);
  const [settingsFor, setSettingsFor] = useState<MCPConnection | null>(null);
  const [installing, setInstalling] = useState<MCPProvider | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mcpError, setMCPError] = useState<string | null>(null);
  const [mcpNotice, setMCPNotice] = useState<string | null>(null);
  // Bumped after a runtime (re)start elsewhere on the page so runtime badges refetch their status.
  const [runtimeVersion, setRuntimeVersion] = useState(0);
  // Connections are the account's: its admins add and change them, every member's agents use them
  const canManage = useCanManageSettings() === true;

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

  const changeTab = (next: string) => {
    const value = next === "social" ? "social" : "mcp";
    setTab(value);
    const params = new URLSearchParams(window.location.search);
    params.set("tab", value);
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
  };

  const items = useMemo(
    () => buildCatalog(providers, connectors, mcpConnections),
    [providers, connectors, mcpConnections]
  );

  const startGoogleConnection = async (connector: ConnectorStatus) => {
    setBusyKey(`google:${connector.connector_id}`);
    setError(null);
    try {
      const response = await connectorApiService.startConnector(connector.connect_path, { return_to: returnToConnectors() });
      window.location.href = response.authorize_url;
    } catch (err) {
      console.error("Error starting connector OAuth:", err);
      setError(`Failed to start ${connector.display_name} connection.`);
      setBusyKey(null);
    }
  };

  const installProvider = async (provider: MCPProvider, inputs: Record<string, string>) => {
    const response = await connectorApiService.installMCPProvider(provider.key, {
      inputs,
      return_to: returnToConnectors(),
    });
    if (response.authorize_url) {
      window.location.assign(response.authorize_url);
      return;
    }
    setInstalling(null);
    await loadConnectors();
  };

  const startProviderInstall = async (provider: MCPProvider) => {
    setDetails(null);
    if (provider.has_inputs) {
      setInstalling(provider);
      return;
    }
    // Nothing to ask the user (e.g. dynamic client registration): straight to sign-in.
    setBusyKey(`mcp:${provider.key}`);
    setMCPError(null);
    try {
      await installProvider(provider, {});
    } catch (err) {
      setMCPError(err instanceof Error ? err.message : `Failed to install ${provider.display_name}.`);
      setBusyKey(null);
    }
  };

  const install = (item: CatalogItem) => {
    if (item.google) void startGoogleConnection(item.google);
    else if (item.provider) void startProviderInstall(item.provider);
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
    const confirmed = window.confirm(`Remove "${connection.name}"?`);
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

  const editConnection = (connection: MCPConnection) => {
    setDetails(null);
    if (connection.provider_key) setSettingsFor(connection);
    else setCustomDialog({ editing: connection });
  };

  const providerFor = (connection: MCPConnection) =>
    providers.find((provider) => provider.key === connection.provider_key) ?? null;

  if (loading) return <LoadingState />;
  if (error && connectors.length === 0 && mcpConnections.length === 0) {
    return <ErrorState message={error} onRetry={loadConnectors} />;
  }

  // Derived from current state, so the dialog follows installs, sign-ins and removals.
  const detailsItem = details?.kind === "item" ? items.find((item) => item.key === details.key) : undefined;
  const detailsCustom = details?.kind === "custom" ? mcpConnections.find((item) => item.mcp_id === details.mcpId) : undefined;
  const detailsProps = {
    providerFor,
    canManage,
    signingInId: startingMCPOAuthId,
    deletingId: deletingMCPId,
    runtimeVersion,
    onSignIn: (connection: MCPConnection) => void startMCPOAuth(connection),
    onEdit: editConnection,
    onDelete: (connection: MCPConnection) => void deleteMCPConnection(connection),
    onClose: () => setDetails(null),
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Account connections</p>
          <h1 className={styles.title}>Connectors</h1>
          <p className={styles.subtitle}>Connect the tools your agents work with.</p>
        </div>
        {tab === "mcp" && (
          <Button variant="outline" onClick={() => void loadConnectors()}>
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
        )}
      </div>

      {!canManage && (
        <p className={styles.note}>
          These connections are your account's. Its admins add and change them; you can enable them on your agents.
        </p>
      )}

      <Tabs value={tab} onValueChange={changeTab}>
        <TabsList>
          <TabsTrigger value="mcp">MCPs</TabsTrigger>
          <TabsTrigger value="social">Social</TabsTrigger>
        </TabsList>
        <TabsContent value="mcp">
          {error && <div className={styles.error}>{error}</div>}
          {mcpError && <div className={styles.error}>{mcpError}</div>}
          {mcpNotice && <div className={styles.notice}>{mcpNotice}</div>}

          <ConnectorCatalog
            items={items}
            connections={mcpConnections}
            canManage={canManage}
            busyKey={busyKey}
            onInstall={install}
            onManage={(item) => setDetails({ kind: "item", key: item.key })}
            onManageCustom={(connection) => setDetails({ kind: "custom", mcpId: connection.mcp_id })}
            onAddCustom={() => setCustomDialog({ editing: null })}
          />
        </TabsContent>
        <TabsContent value="social">
          <SocialAccountsTab canManage={canManage} />
        </TabsContent>
      </Tabs>

      {detailsItem?.installed && (
        <ConnectorDetailsDialog
          {...detailsProps}
          title={detailsItem.name}
          description={detailsItem.description}
          icon={detailsItem.icon}
          connections={detailsItem.connections}
          footer={
            canManage && (
              <div className={styles.actions}>
                {detailsItem.google && (
                  <Button variant="outline" onClick={() => install(detailsItem)} disabled={busyKey === detailsItem.key}>
                    <RefreshCw className="h-4 w-4" />
                    {busyKey === detailsItem.key ? "Opening..." : "Reconnect"}
                  </Button>
                )}
                {detailsItem.provider && (
                  <Button variant="outline" onClick={() => install(detailsItem)}>
                    <CheckCircle className="h-4 w-4" />
                    Add another
                  </Button>
                )}
              </div>
            )
          }
        />
      )}

      {detailsCustom && (
        <ConnectorDetailsDialog
          {...detailsProps}
          title={detailsCustom.name}
          description="A server you added. Enable it per agent from the agent settings."
          icon={connectionIcon(detailsCustom)}
          connections={[detailsCustom]}
        />
      )}

      {installing && (
        <SchemaFormDialog
          key={installing.key}
          title={`Install ${installing.display_name}`}
          description={
            installing.has_sign_in
              ? "Enter these details, then sign in to finish connecting."
              : "Enter these details to connect."
          }
          submitLabel={installing.has_sign_in ? "Continue to sign in" : "Install"}
          loadSchema={() => connectorApiService.getMCPProviderInstallForm(installing.key)}
          onSubmit={(inputs) => installProvider(installing, inputs)}
          onClose={() => setInstalling(null)}
        />
      )}

      {customDialog && (
        <CustomMCPDialog
          key={customDialog.editing?.mcp_id ?? "new"}
          editing={customDialog.editing}
          onClose={() => setCustomDialog(null)}
          onSaved={async () => {
            setCustomDialog(null);
            await loadConnectors();
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
            await loadConnectors();
          }}
          onClose={() => setSettingsFor(null)}
        />
      )}
    </div>
  );
}
