import { useState } from "react";
import { Download, ExternalLink } from "lucide-react";

import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, StatusBadge } from "../../../components/ui";
import { connectorApiService } from "../../../services/connectors";
import type { MCPProvider } from "../../../types/connectors";
import { IconBox, ProviderIcon } from "./connectorUi";
import { returnToConnectors } from "./connectorUrls";
import { SchemaFormDialog } from "./SchemaFormDialog";

interface MCPProviderCatalogProps {
  providers: MCPProvider[];
  onInstalled: () => Promise<void>;
  onError: (message: string) => void;
}

/** Curated providers, configured in the backend. Install asks only for what the user must supply. */
export function MCPProviderCatalog({ providers, onInstalled, onError }: MCPProviderCatalogProps) {
  const [installing, setInstalling] = useState<MCPProvider | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const install = async (provider: MCPProvider, inputs: Record<string, string>) => {
    const response = await connectorApiService.installMCPProvider(provider.key, {
      inputs,
      return_to: returnToConnectors(),
    });
    if (response.authorize_url) {
      window.location.assign(response.authorize_url);
      return;
    }
    setInstalling(null);
    await onInstalled();
  };

  const startInstall = async (provider: MCPProvider) => {
    if (provider.has_inputs) {
      setInstalling(provider);
      return;
    }
    // Nothing to ask the user (e.g. dynamic client registration): straight to sign-in.
    setBusyKey(provider.key);
    try {
      await install(provider, {});
    } catch (err) {
      onError(err instanceof Error ? err.message : `Failed to install ${provider.display_name}.`);
      setBusyKey(null);
    }
  };

  return (
    <>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(16rem, 1fr))", gap: "1rem" }}>
        {providers.map((provider) => (
          <Card key={provider.key}>
            <CardHeader>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "center" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                  <IconBox>
                    <ProviderIcon icon={provider.icon} />
                  </IconBox>
                  <div>
                    <CardTitle>{provider.display_name}</CardTitle>
                    <CardDescription>{provider.transport === "stdio" ? "Hosted by InnoMight Labs" : "Remote MCP"}</CardDescription>
                  </div>
                </div>
                {provider.installed_count > 0 && <StatusBadge status="active" label="Installed" size="sm" />}
              </div>
            </CardHeader>
            <CardContent>
              <div style={{ display: "grid", gap: "0.875rem" }}>
                <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", lineHeight: 1.6 }}>{provider.description}</p>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  <Button onClick={() => void startInstall(provider)} disabled={busyKey === provider.key}>
                    <Download className="h-4 w-4" />
                    {busyKey === provider.key ? "Opening..." : provider.installed_count > 0 ? "Install another" : "Install"}
                  </Button>
                  <Button variant="ghost" onClick={() => window.open(provider.docs_url, "_blank", "noopener")}>
                    <ExternalLink className="h-4 w-4" />
                    Docs
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

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
          onSubmit={(inputs) => install(installing, inputs)}
          onClose={() => setInstalling(null)}
        />
      )}
    </>
  );
}
