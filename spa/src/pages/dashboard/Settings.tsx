import { useEffect, useState } from "react";
import { Settings as SettingsIcon, CheckCircle, AlertCircle, Loader2 } from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { SchemaForm } from "../../components/forms";
import { authService } from "../../services/auth";
import { httpClient } from "../../services/http";
import {
  providerSettingsService,
  type ProviderWithStatus,
} from "../../services/settings/ProviderSettingsService";

type SubscriptionStatus = {
  tier: string;
  status?: string | null;
  current_period_end?: string | null;
  is_active: boolean;
};

export function Settings() {
  const [providers, setProviders] = useState<ProviderWithStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [subscription, setSubscription] = useState<SubscriptionStatus | null>(null);
  const [subscriptionLoading, setSubscriptionLoading] = useState(true);

  // Track which provider is being configured
  const [configuringProvider, setConfiguringProvider] = useState<string | null>(null);
  const [savingProvider, setSavingProvider] = useState(false);

  // Get user info from token
  const userInfo = authService.getUserFromToken();

  useEffect(() => {
    loadProviders();
    loadSubscription();
  }, []);

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

  const handleSaveProvider = async (providerName: string, data: Record<string, string>) => {
    setSavingProvider(true);
    setError(null);
    try {
      await providerSettingsService.saveProviderSettings(providerName, data);
      // Refresh providers list to update status
      await loadProviders();
      setConfiguringProvider(null);
    } catch (err) {
      setError("Failed to save provider configuration. Please try again.");
      console.error("Error saving provider:", err);
    } finally {
      setSavingProvider(false);
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

  const formatPeriodEnd = (value?: string | null) => {
    if (!value) return "—";
    if (/^\d+$/.test(value)) {
      const date = new Date(Number(value) * 1000);
      return isNaN(date.getTime()) ? "—" : date.toLocaleDateString();
    }
    const date = new Date(value);
    return isNaN(date.getTime()) ? "—" : date.toLocaleDateString();
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", maxWidth: "42rem" }}>
      {/* Profile Section */}
      <Card>
        <CardHeader>
          <CardTitle>Profile Settings</CardTitle>
          <CardDescription>
            Your account information from Google
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <Label htmlFor="displayName">Display Name</Label>
              <Input
                id="displayName"
                value={userInfo?.name || ""}
                disabled
                style={{ backgroundColor: "var(--bg-tertiary)" }}
              />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={userInfo?.email || ""}
                disabled
                style={{ backgroundColor: "var(--bg-tertiary)" }}
              />
            </div>
            <p style={{ fontSize: "0.875rem", color: "var(--text-muted)" }}>
              Profile settings are managed through your Google account
            </p>
          </div>
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
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
              <Loader2 className="h-4 w-4 animate-spin" style={{ color: "var(--gradient-start)" }} />
              <span style={{ color: "var(--text-muted)" }}>Loading subscription...</span>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--text-muted)" }}>Plan</span>
                <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                  {subscription?.tier ?? "free"}
                </span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--text-muted)" }}>Status</span>
                <span style={{ color: "var(--text-primary)" }}>
                  {subscription?.status ?? "free"}
                </span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--text-muted)" }}>Renewal date</span>
                <span style={{ color: "var(--text-primary)" }}>
                  {formatPeriodEnd(subscription?.current_period_end)}
                </span>
              </div>
              <div>
                <a href="/pricing" style={{ color: "var(--text-primary)", textDecoration: "underline" }}>
                  Manage plan
                </a>
              </div>
            </div>
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
          {error && (
            <div
              style={{
                marginBottom: "1rem",
                padding: "0.75rem",
                borderRadius: "0.5rem",
                backgroundColor: "rgba(248, 113, 113, 0.1)",
                border: "1px solid rgba(248, 113, 113, 0.2)",
                color: "#f87171",
                fontSize: "0.875rem",
              }}
            >
              {error}
            </div>
          )}

          {loading ? (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "2rem" }}>
              <Loader2 className="h-6 w-6 animate-spin" style={{ color: "var(--gradient-start)" }} />
            </div>
          ) : providers.length === 0 ? (
            <p style={{ color: "var(--text-muted)", textAlign: "center", padding: "2rem" }}>
              No providers available
            </p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              {providers.map((provider) => (
                <div
                  key={provider.provider_name}
                  style={{
                    padding: "1rem",
                    borderRadius: "0.5rem",
                    border: "1px solid var(--border-subtle)",
                    backgroundColor: "var(--bg-secondary)",
                  }}
                >
                  {configuringProvider === provider.provider_name ? (
                    // Show configuration form
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem" }}>
                        <SettingsIcon className="h-5 w-5" style={{ color: "var(--gradient-start)" }} />
                        <h3 style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                          Configure {provider.provider_name}
                        </h3>
                      </div>
                      <SchemaForm
                        schema={provider.form}
                        onSubmit={(data) => handleSaveProvider(provider.provider_name, data)}
                        onCancel={handleCancelConfigure}
                        submitLabel="Save Configuration"
                        isLoading={savingProvider}
                      />
                    </div>
                  ) : (
                    // Show provider card
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                        {provider.is_configured ? (
                          <CheckCircle className="h-5 w-5" style={{ color: "#4ade80" }} />
                        ) : (
                          <AlertCircle className="h-5 w-5" style={{ color: "var(--text-muted)" }} />
                        )}
                        <div>
                          <p style={{ fontWeight: 500, color: "var(--text-primary)" }}>
                            {provider.provider_name}
                          </p>
                          <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                            {provider.is_configured ? "Configured" : "Not configured"}
                          </p>
                        </div>
                      </div>
                      <Button
                        variant={provider.is_configured ? "outline" : "default"}
                        size="sm"
                        onClick={() => handleConfigureClick(provider.provider_name)}
                      >
                        {provider.is_configured ? "Update" : "Configure"}
                      </Button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
