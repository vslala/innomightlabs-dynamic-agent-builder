import { useEffect, useState } from "react";
import { Settings as SettingsIcon, CheckCircle, AlertCircle, Loader2, Palette } from "lucide-react";
import { cn } from "../../lib/utils";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  SectionCardHeader,
  Button,
  Input,
  Label,
  AlertBanner,
  LoadingState,
  InlineEmptyState,
  ListRow,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../components/ui";
import { FieldGroup, Grid, Inline, PageBody, Stack } from "../../components/layout";
import { SchemaForm } from "../../components/forms";
import type { FormSchema, FormValue } from "../../types/form";
import { ConfirmationDialog } from "../../components/ui/confirmation-dialog";
import { authService } from "../../services/auth";
import { httpClient } from "../../services/http";
import {
  providerSettingsService,
  type ProviderWithStatus,
} from "../../services/settings/ProviderSettingsService";
import {
  agent2AgentSettingsService,
  type Agent2AgentSettings,
} from "../../services/settings/Agent2AgentSettingsService";
import {
  smartSuggestionService,
  type SmartSuggestionSettings,
} from "../../services/smartSuggestions";
import { agentApiService, type AgentResponse } from "../../services/agents/AgentApiService";
import { defaultAgentService } from "../../services/settings/DefaultAgentService";
import { getStoredTheme, setStoredTheme, type AppTheme } from "../../lib/theme";
import styles from "./Settings.module.css";

type SubscriptionStatus = {
  tier: string;
  status?: string | null;
  current_period_start?: string | null;
  current_period_end?: string | null;
  is_active: boolean;
  cancel_at_period_end?: boolean | null;
};

const isKeyValueRecord = (value: FormValue): value is Record<string, string> => (
  value !== null
  && typeof value === "object"
  && !(value instanceof FileList)
  && !Array.isArray(value)
);

export function Settings() {
  const [providers, setProviders] = useState<ProviderWithStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [subscription, setSubscription] = useState<SubscriptionStatus | null>(null);
  const [subscriptionLoading, setSubscriptionLoading] = useState(true);
  const [cancellingSubscription, setCancellingSubscription] = useState(false);
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);
  const [openaiConnecting, setOpenaiConnecting] = useState(false);
  const [openaiDisconnecting, setOpenaiDisconnecting] = useState(false);
  const [smartSuggestionSettings, setSmartSuggestionSettings] = useState<SmartSuggestionSettings | null>(null);
  const [smartSuggestionSchema, setSmartSuggestionSchema] = useState<FormSchema | null>(null);
  const [smartSuggestionLoading, setSmartSuggestionLoading] = useState(true);
  const [smartSuggestionSaving, setSmartSuggestionSaving] = useState(false);
  const [agent2AgentSettings, setAgent2AgentSettings] = useState<Agent2AgentSettings | null>(null);
  const [agent2AgentSchema, setAgent2AgentSchema] = useState<FormSchema | null>(null);
  const [agent2AgentLoading, setAgent2AgentLoading] = useState(true);
  const [agent2AgentSaving, setAgent2AgentSaving] = useState(false);
  const [theme, setTheme] = useState<AppTheme>(() => getStoredTheme());
  const [agents, setAgents] = useState<AgentResponse[]>([]);
  const [defaultAgentId, setDefaultAgentId] = useState<string | null>(null);
  const [defaultAgentLoading, setDefaultAgentLoading] = useState(true);
  const [defaultAgentSaving, setDefaultAgentSaving] = useState(false);

  // Track which provider is being configured
  const [configuringProvider, setConfiguringProvider] = useState<string | null>(null);
  const [savingProvider, setSavingProvider] = useState(false);

  // Get user info from token
  const userInfo = authService.getUserFromToken();

  useEffect(() => {
    loadProviders();
    loadSubscription();
    loadSmartSuggestionSettings();
    loadAgent2AgentSettings();
    loadDefaultAgentSettings();
  }, []);

  const getErrorMessage = (err: unknown, fallback: string) => {
    if (err && typeof err === "object" && "response" in err) {
      const response = (err as { response?: { data?: { detail?: string } } }).response;
      const detail = response?.data?.detail;
      if (typeof detail === "string" && detail.trim()) {
        return detail;
      }
    }
    return fallback;
  };

  const loadProviders = async () => {
    try {
      setError(null);
      const data = await providerSettingsService.listProviders();
      setProviders(data);
    } catch (err) {
      setError("Failed to load providers. Please try again.");
      console.error("Error loading providers:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleConfigureClick = (providerName: string) => {
    setConfiguringProvider(providerName);
    setError(null);
  };

  const handleCancelConfigure = () => {
    setConfiguringProvider(null);
  };

  const handleSaveProvider = async (providerName: string, data: Record<string, FormValue>) => {
    setSavingProvider(true);
    setError(null);
    try {
      if (providerName === "OpenAI") {
        const callbackUrl = typeof data.callback_url === "string" ? data.callback_url.trim() : "";
        await providerSettingsService.completeOpenAIConnect({ callback_url: callbackUrl });
      } else {
        const payload: Record<string, string> = {};
        for (const [key, value] of Object.entries(data)) {
          if (typeof value === "string") {
            payload[key] = value;
          }
        }
        await providerSettingsService.saveProviderSettings(providerName, payload);
      }
      // Refresh providers list to update status
      await loadProviders();
      setConfiguringProvider(null);
    } catch (err) {
      setError(getErrorMessage(err, "Failed to save provider configuration. Please try again."));
      console.error("Error saving provider:", err);
    } finally {
      setSavingProvider(false);
    }
  };

  const handleOpenAIConnect = async () => {
    setOpenaiConnecting(true);
    setError(null);
    try {
      const response = await providerSettingsService.startOpenAIConnect();
      const opened = window.open(response.authorize_url, "_blank", "noopener,noreferrer");
      if (!opened) {
        setError("Popup blocked. Please allow popups and try again.");
      }
    } catch (err) {
      setError(getErrorMessage(err, "Failed to start OpenAI OAuth connection. Please try again."));
      console.error("Error starting OpenAI OAuth:", err);
    } finally {
      setOpenaiConnecting(false);
    }
  };

  const handleOpenAIDisconnect = async () => {
    setOpenaiDisconnecting(true);
    setError(null);
    try {
      await providerSettingsService.deleteProviderSettings("OpenAI");
      await loadProviders();
      if (configuringProvider === "OpenAI") {
        setConfiguringProvider(null);
      }
    } catch (err) {
      setError(getErrorMessage(err, "Failed to disconnect OpenAI. Please try again."));
      console.error("Error disconnecting OpenAI:", err);
    } finally {
      setOpenaiDisconnecting(false);
    }
  };

  const loadSubscription = async () => {
    try {
      const data = await httpClient.get<SubscriptionStatus>("/payments/stripe/subscription/status");
      setSubscription(data);
    } catch {
      setSubscription(null);
    } finally {
      setSubscriptionLoading(false);
    }
  };

  const loadSmartSuggestionSettings = async () => {
    setSmartSuggestionLoading(true);
    try {
      const [settings, schema] = await Promise.all([
        smartSuggestionService.getSettings(),
        smartSuggestionService.getSettingsSchema(),
      ]);
      setSmartSuggestionSettings(settings);
      setSmartSuggestionSchema(schema);
    } catch (err) {
      setError(getErrorMessage(err, "Failed to load smart suggestion settings. Please try again."));
      console.error("Error loading smart suggestion settings:", err);
    } finally {
      setSmartSuggestionLoading(false);
    }
  };

  const handleSaveSmartSuggestionSettings = async (data: Record<string, FormValue>) => {
    setSmartSuggestionSaving(true);
    setError(null);
    try {
      const enabled = data.enabled === "true";
      const providerName = typeof data.provider_name === "string" ? data.provider_name : "";
      const modelName = typeof data.model_name === "string" ? data.model_name : "";
      const settings = await smartSuggestionService.saveSettings({
        enabled,
        provider_name: enabled ? providerName : null,
        model_name: enabled ? modelName : null,
      });
      setSmartSuggestionSettings(settings);
      await loadSmartSuggestionSettings();
    } catch (err) {
      setError(getErrorMessage(err, "Failed to save smart suggestion settings. Please try again."));
      console.error("Error saving smart suggestion settings:", err);
    } finally {
      setSmartSuggestionSaving(false);
    }
  };

  const loadAgent2AgentSettings = async () => {
    setAgent2AgentLoading(true);
    try {
      const [settings, schema] = await Promise.all([
        agent2AgentSettingsService.getSettings(),
        agent2AgentSettingsService.getSettingsSchema(),
      ]);
      setAgent2AgentSettings(settings);
      setAgent2AgentSchema(schema);
    } catch (err) {
      setError(getErrorMessage(err, "Failed to load Agent2Agent settings. Please try again."));
      console.error("Error loading Agent2Agent settings:", err);
    } finally {
      setAgent2AgentLoading(false);
    }
  };

  const handleSaveAgent2AgentSettings = async (data: Record<string, FormValue>) => {
    setAgent2AgentSaving(true);
    setError(null);
    try {
      const allowedOrigins = data.allowed_origins;
      const settings = await agent2AgentSettingsService.saveSettings({
        allowed_origins: isKeyValueRecord(allowedOrigins) ? allowedOrigins : {},
      });
      setAgent2AgentSettings(settings);
      await loadAgent2AgentSettings();
    } catch (err) {
      setError(getErrorMessage(err, "Failed to save Agent2Agent settings. Please try again."));
      console.error("Error saving Agent2Agent settings:", err);
    } finally {
      setAgent2AgentSaving(false);
    }
  };

  const loadDefaultAgentSettings = async () => {
    setDefaultAgentLoading(true);
    try {
      const [agentsData, preference] = await Promise.all([
        agentApiService.listAgents(),
        defaultAgentService.getDefaultAgent(),
      ]);
      setAgents(agentsData);
      // A default agent that's been deleted/lost access is treated as unset, not an error.
      setDefaultAgentId(
        agentsData.some((agent) => agent.agent_id === preference.agent_id) ? preference.agent_id : null
      );
    } catch (err) {
      setError(getErrorMessage(err, "Failed to load default agent settings. Please try again."));
      console.error("Error loading default agent settings:", err);
    } finally {
      setDefaultAgentLoading(false);
    }
  };

  const handleSetDefaultAgent = async (agentId: string) => {
    setDefaultAgentSaving(true);
    setError(null);
    try {
      const preference = await defaultAgentService.setDefaultAgent(agentId);
      setDefaultAgentId(preference.agent_id);
    } catch (err) {
      setError(getErrorMessage(err, "Failed to set default agent. Please try again."));
      console.error("Error setting default agent:", err);
    } finally {
      setDefaultAgentSaving(false);
    }
  };

  const handleClearDefaultAgent = async () => {
    setDefaultAgentSaving(true);
    setError(null);
    try {
      await defaultAgentService.clearDefaultAgent();
      setDefaultAgentId(null);
    } catch (err) {
      setError(getErrorMessage(err, "Failed to clear default agent. Please try again."));
      console.error("Error clearing default agent:", err);
    } finally {
      setDefaultAgentSaving(false);
    }
  };

  const handleCancelSubscription = async () => {
    if (!subscription?.is_active) return;

    setCancellingSubscription(true);
    setError(null);
    try {
      await httpClient.post("/payments/stripe/subscription/cancel", {});
      // Reload subscription to reflect cancellation status
      await loadSubscription();
      setShowCancelConfirm(false);
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const httpError = err as { response?: { data?: { detail?: string } } };
        setError(httpError.response?.data?.detail || "Failed to cancel subscription. Please try again.");
      } else {
        setError("Failed to cancel subscription. Please try again.");
      }
      console.error("Error cancelling subscription:", err);
    } finally {
      setCancellingSubscription(false);
    }
  };

  const formatPeriodEnd = (value?: string | null) => {
    if (!value) return "—";
    if (/^\d+$/.test(value)) {
      const date = new Date(Number(value) * 1000);
      return isNaN(date.getTime()) ? "—" : date.toLocaleDateString();
    }
    const date = new Date(value);
    return isNaN(date.getTime()) ? "—" : date.toLocaleDateString();
  };

  const formatBillingPeriod = (start?: string | null, end?: string | null) => {
    const startFormatted = formatPeriodEnd(start);
    const endFormatted = formatPeriodEnd(end);

    if (startFormatted === "—" && endFormatted === "—") return "—";
    if (startFormatted === "—") return endFormatted;
    if (endFormatted === "—") return startFormatted;

    return `${startFormatted} - ${endFormatted}`;
  };

  const handleThemeChange = (nextTheme: AppTheme) => {
    setTheme(nextTheme);
    setStoredTheme(nextTheme);
  };

  return (
    <PageBody style={{ maxWidth: "42rem" }}>
      {/* Profile Section */}
      <Card>
        <CardHeader>
          <CardTitle>Profile Settings</CardTitle>
          <CardDescription>
            Your account information from Google
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Stack className={styles.stackGap4}>
            <FieldGroup>
              <Label htmlFor="displayName">Display Name</Label>
              <Input
                id="displayName"
                value={userInfo?.name || ""}
                disabled
                className={styles.disabledFieldBg}
              />
            </FieldGroup>
            <FieldGroup>
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={userInfo?.email || ""}
                disabled
                className={styles.disabledFieldBg}
              />
            </FieldGroup>
            <p className={styles.profileNote}>
              Profile settings are managed through your Google account
            </p>
          </Stack>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Appearance</CardTitle>
          <CardDescription>
            Choose how the dashboard looks on this device.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Grid className={styles.appearanceGrid} gap="sm">
            {[
              {
                id: "dark" as const,
                label: "Dark",
                description: "Dark neutral surfaces with a crisp blue accent.",
                swatches: ["#101214", "#579dff", "#1d2125"],
              },
              {
                id: "light" as const,
                label: "Light",
                description: "Clean light surfaces with a crisp blue accent.",
                swatches: ["#f7f8f9", "#0c66e4", "#ffffff"],
              },
            ].map((option) => {
              const selected = theme === option.id;
              return (
                <Button
                  key={option.id}
                  type="button"
                  variant="ghost"
                  onClick={() => handleThemeChange(option.id)}
                  className={cn(
                    styles.themeOptionButton,
                    selected ? styles.themeOptionSelected : styles.themeOptionUnselected
                  )}
                >
                  <div className={styles.themeOptionTopRow}>
                    <div className={styles.themeOptionLabelRow}>
                      <Palette className={styles.themeOptionIcon} />
                      <span className={styles.themeOptionLabel}>{option.label}</span>
                    </div>
                    {selected && <CheckCircle className={styles.themeOptionIcon} />}
                  </div>
                  <div className={styles.themeSwatchRow}>
                    {option.swatches.map((color) => (
                      <span
                        key={color}
                        className={styles.themeSwatch}
                        style={{ background: color }}
                      />
                    ))}
                  </div>
                  <p className={styles.themeOptionDescription}>
                    {option.description}
                  </p>
                </Button>
              );
            })}
          </Grid>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Default Agent</CardTitle>
          <CardDescription>
            Automatically preselect an agent whenever you start a new conversation.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {defaultAgentLoading ? (
            <div className={styles.loadingRow}>
              <Loader2 className={styles.sectionLoadingSpinner} />
            </div>
          ) : agents.length === 0 ? (
            <p className={styles.mutedText}>Create an agent first to set a default.</p>
          ) : (
            <Stack gap="sm">
              <FieldGroup>
                <Label htmlFor="default-agent">Default agent</Label>
                <Select
                  value={defaultAgentId ?? ""}
                  onValueChange={handleSetDefaultAgent}
                  disabled={defaultAgentSaving}
                >
                  <SelectTrigger id="default-agent">
                    <SelectValue placeholder="No default — choose manually each time" />
                  </SelectTrigger>
                  <SelectContent>
                    {agents.map((agent) => (
                      <SelectItem key={agent.agent_id} value={agent.agent_id}>
                        {agent.agent_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </FieldGroup>
              {defaultAgentId && (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={handleClearDefaultAgent}
                  disabled={defaultAgentSaving}
                >
                  Clear default
                </Button>
              )}
            </Stack>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Subscription</CardTitle>
          <CardDescription>
            Your current plan, billing status, and renewal date.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {subscriptionLoading ? (
            <Inline gap="sm">
              <Loader2 className={styles.subscriptionSpinner} />
              <span className={styles.subscriptionLoadingText}>Loading subscription...</span>
            </Inline>
          ) : (
            <Stack gap="sm">
              <Inline justify="space-between">
                <span className={styles.subscriptionLabel}>Plan</span>
                <span className={styles.subscriptionTierValue}>
                  {subscription?.tier ?? "free"}
                </span>
              </Inline>
              <Inline justify="space-between">
                <span className={styles.subscriptionLabel}>Status</span>
                <span className={styles.subscriptionValue}>
                  {subscription?.status ?? "free"}
                </span>
              </Inline>
              <Inline justify="space-between">
                <span className={styles.subscriptionLabel}>Billing period</span>
                <span className={styles.subscriptionValue}>
                  {formatBillingPeriod(subscription?.current_period_start, subscription?.current_period_end)}
                </span>
              </Inline>
              {subscription?.cancel_at_period_end ? (
                <AlertBanner
                  variant="warning"
                  message={
                    subscription?.current_period_end
                      ? `Subscription will be cancelled on ${formatPeriodEnd(subscription.current_period_end)}. You'll continue to have access until then.`
                      : "Subscription is scheduled for cancellation. You'll continue to have access until the end of your current billing period."
                  }
                />
              ) : (
                <>
                  <Inline gap="sm">
                    <a
                      href="/pricing"
                      className={styles.upgradeLink}
                    >
                      {subscription?.is_active
                        ? `Upgrade plan (current: ${subscription.tier})`
                        : "Choose a plan"
                      }
                    </a>
                    {subscription?.is_active && subscription.tier !== "free" && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setShowCancelConfirm(true)}
                        disabled={cancellingSubscription}
                        className={styles.cancelSubscriptionButton}
                      >
                        Cancel Subscription
                      </Button>
                    )}
                  </Inline>
                  {subscription?.is_active && (
                    <p className={styles.downgradeHint}>
                      To downgrade, contact support
                    </p>
                  )}
                </>
              )}
            </Stack>
          )}
        </CardContent>
      </Card>

      {/* Provider Configuration Section */}
      <Card>
        <CardHeader>
          <CardTitle>Provider Configuration</CardTitle>
          <CardDescription>
            Configure API credentials for LLM providers
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Stack gap="sm">
            {error && <AlertBanner message={error} variant="error" />}

            {loading ? (
              <LoadingState className={styles.providersLoadingState} size="default" />
            ) : providers.length === 0 ? (
              <InlineEmptyState icon={AlertCircle} title="No providers available" />
            ) : (
              <Stack className={styles.stackGap4}>
                {providers.map((provider) =>
                  configuringProvider === provider.provider_name ? (
                    // Show configuration form
                    <div
                      key={provider.provider_name}
                      className={styles.providerConfigPanel}
                    >
                      <Stack className={styles.stackGap4}>
                        <SectionCardHeader icon={SettingsIcon} title={`Configure ${provider.provider_name}`} />
                        {provider.provider_name === "OpenAI" && (
                          <div className={styles.oauthGuide}>
                            <p className={styles.oauthGuideText}>
                              1. Click Open OpenAI Login. 2. Sign in and approve access. 3. Copy the full localhost callback URL from your browser (the page may fail to load). 4. Paste that URL below and submit.
                            </p>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={handleOpenAIConnect}
                              disabled={openaiConnecting}
                            >
                              {openaiConnecting ? "Opening..." : "Open OpenAI Login"}
                            </Button>
                          </div>
                        )}
                        <SchemaForm
                          schema={provider.form}
                          onSubmit={(data) => handleSaveProvider(provider.provider_name, data)}
                          onCancel={handleCancelConfigure}
                          submitLabel={provider.provider_name === "OpenAI" ? "Complete Connection" : "Save Configuration"}
                          isLoading={savingProvider}
                        />
                      </Stack>
                    </div>
                  ) : (
                    // Show provider row
                    <ListRow
                      key={provider.provider_name}
                      icon={
                        provider.is_configured ? (
                          <CheckCircle className={styles.providerConfiguredIcon} />
                        ) : (
                          <AlertCircle className={styles.providerUnconfiguredIcon} />
                        )
                      }
                      title={provider.provider_name === "OpenAI" ? "OpenAI (OAuth)" : provider.provider_name}
                      subtitle={
                        provider.provider_name === "OpenAI"
                          ? (provider.is_configured ? "Connected via OAuth" : "Not connected")
                          : (provider.is_configured ? "Configured" : "Not configured")
                      }
                      trailing={
                        <Inline gap="xs" wrap={false}>
                          {provider.provider_name === "OpenAI" && provider.is_configured && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={handleOpenAIDisconnect}
                              disabled={openaiDisconnecting}
                            >
                              {openaiDisconnecting ? "Disconnecting..." : "Disconnect"}
                            </Button>
                          )}
                          <Button
                            variant={provider.is_configured ? "outline" : "default"}
                            size="sm"
                            onClick={() => handleConfigureClick(provider.provider_name)}
                          >
                            {provider.provider_name === "OpenAI"
                              ? (provider.is_configured ? "Reconnect" : "Connect")
                              : (provider.is_configured ? "Update" : "Configure")}
                          </Button>
                        </Inline>
                      }
                    />
                  )
                )}
              </Stack>
            )}
          </Stack>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Agent2Agent</CardTitle>
          <CardDescription>
            Allow outbound Agent2Agent registry and service origins before agents can install or use A2A client skills.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {agent2AgentLoading ? (
            <div className={styles.loadingRow}>
              <Loader2 className={styles.sectionLoadingSpinner} />
            </div>
          ) : agent2AgentSchema ? (
            <div className={styles.formSection}>
              <div className={styles.statusRow}>
                {agent2AgentSettings?.allowed_origins.length ? (
                  <CheckCircle className={cn(styles.statusIcon, styles.statusIconSuccess)} />
                ) : (
                  <AlertCircle className={styles.statusIcon} />
                )}
                <p className={styles.mutedText}>
                  {agent2AgentSettings?.allowed_origins.length
                    ? `${agent2AgentSettings.allowed_origins.length} origin${agent2AgentSettings.allowed_origins.length === 1 ? "" : "s"} allowlisted.`
                    : "No Agent2Agent origins are allowlisted. A2A client skill installs and calls will be blocked."}
                </p>
              </div>
              <SchemaForm
                key={JSON.stringify(agent2AgentSettings?.allowed_origins_map ?? {})}
                schema={agent2AgentSchema}
                initialValues={{ allowed_origins: agent2AgentSettings?.allowed_origins_map ?? {} }}
                onSubmit={handleSaveAgent2AgentSettings}
                submitLabel="Save Agent2Agent Settings"
                isLoading={agent2AgentSaving}
              />
            </div>
          ) : (
            <p className={styles.mutedText}>Agent2Agent settings are unavailable.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Smart Suggestions</CardTitle>
          <CardDescription>
            Choose the model used by schema-driven field suggestions.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {smartSuggestionLoading ? (
            <div className={styles.loadingRow}>
              <Loader2 className={styles.sectionLoadingSpinner} />
            </div>
          ) : smartSuggestionSchema ? (
            <div className={styles.formSection}>
              <div className={styles.statusRow}>
                {smartSuggestionSettings?.is_configured ? (
                  <CheckCircle className={cn(styles.statusIcon, styles.statusIconSuccess)} />
                ) : (
                  <AlertCircle className={styles.statusIcon} />
                )}
                <p className={styles.mutedText}>
                  {smartSuggestionSettings?.is_configured
                    ? `Enabled with ${smartSuggestionSettings.provider_name} / ${smartSuggestionSettings.model_name}`
                    : "Configure a provider and model before using smart suggestions in forms."}
                </p>
              </div>
              <SchemaForm
                key={`${smartSuggestionSettings?.enabled}-${smartSuggestionSettings?.provider_name}-${smartSuggestionSettings?.model_name}`}
                schema={smartSuggestionSchema}
                onSubmit={handleSaveSmartSuggestionSettings}
                submitLabel="Save Smart Suggestions"
                isLoading={smartSuggestionSaving}
              />
            </div>
          ) : (
            <p className={styles.mutedText}>Smart suggestion settings are unavailable.</p>
          )}
        </CardContent>
      </Card>

      {/* Cancel Subscription Confirmation Dialog */}
      <ConfirmationDialog
        open={showCancelConfirm}
        onOpenChange={setShowCancelConfirm}
        title="Cancel Subscription"
        description={`Are you sure you want to cancel your ${subscription?.tier} subscription? You'll continue to have access until ${formatPeriodEnd(subscription?.current_period_end)}.`}
        confirmText="Yes, Cancel"
        cancelText="Keep Subscription"
        onConfirm={handleCancelSubscription}
        variant="destructive"
        loading={cancellingSubscription}
        loadingText="Cancelling..."
      />
    </PageBody>
  );
}
