import { useCallback, useEffect, useState } from "react";
import { AlertCircle, CheckCircle, Loader2 } from "lucide-react";
import { cn } from "../../lib/utils";
import { AlertBanner, Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../components/ui";
import { SchemaForm } from "../../components/forms";
import type { FormSchema, FormValue } from "../../types/form";
import { imageGenerationSettingsService, type ImageGenerationSettings } from "../../services/imageGeneration";
import { useCanManageSettings } from "../../hooks/useCanManageSettings";
import styles from "./Settings.module.css";

/** Shown to members: the account's admins manage this, and every member's agents use it. */
const MANAGED_BY_ADMINS = "Your account's admins manage this. Your agents use it.";

/**
 * The account's image generation: when on, agents can draw with the provider and model chosen here, which is
 * separate from the agent's own model. The Image Generation skill can only be installed once it is on.
 */
export function ImageGenerationSettingsCard() {
  const canManage = useCanManageSettings() === true;
  const [settings, setSettings] = useState<ImageGenerationSettings | null>(null);
  const [schema, setSchema] = useState<FormSchema | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [loadedSettings, loadedSchema] = await Promise.all([
        imageGenerationSettingsService.getSettings(),
        imageGenerationSettingsService.getSettingsSchema(),
      ]);
      setSettings(loadedSettings);
      setSchema(loadedSchema);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load image generation settings. Please try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async (data: Record<string, FormValue>) => {
    setSaving(true);
    setError(null);
    try {
      const enabled = data.enabled === "true";
      const providerName = typeof data.provider_name === "string" ? data.provider_name : "";
      const modelName = typeof data.model_name === "string" ? data.model_name : "";
      await imageGenerationSettingsService.saveSettings({
        enabled,
        provider_name: enabled ? providerName : null,
        model_name: enabled ? modelName : null,
      });
      await load();
    } catch (err) {
      // The API says why a model was refused ("That model can't draw images"), so show its words.
      setError(err instanceof Error ? err.message : "Failed to save image generation settings. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Image Generation</CardTitle>
        <CardDescription>
          Lets agents draw images. They draw with the provider and image model chosen here, separate from the agent&apos;s
          own model, so an agent on any provider can use it. The Image Generation skill needs this turned on first.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error && <AlertBanner message={error} variant="error" />}
        {loading ? (
          <div className={styles.loadingRow}>
            <Loader2 className={styles.sectionLoadingSpinner} />
          </div>
        ) : schema ? (
          <div className={styles.formSection}>
            <div className={styles.statusRow}>
              {settings?.is_configured ? (
                <CheckCircle className={cn(styles.statusIcon, styles.statusIconSuccess)} />
              ) : (
                <AlertCircle className={styles.statusIcon} />
              )}
              <p className={styles.mutedText}>
                {settings?.is_configured
                  ? `Enabled with ${settings.provider_name} / ${settings.model_name}`
                  : "Off. Choose a provider and an image model to let agents draw."}
              </p>
            </div>
            {canManage ? (
              <>
                <SchemaForm
                  key={`${settings?.enabled}-${settings?.provider_name}-${settings?.model_name}`}
                  schema={schema}
                  onSubmit={save}
                  submitLabel="Save Image Generation"
                  isLoading={saving}
                />
                <p className={styles.mutedText}>
                  The agent sends the picture&apos;s description to this provider to have it drawn.
                </p>
              </>
            ) : (
              <p className={styles.mutedText}>{MANAGED_BY_ADMINS}</p>
            )}
          </div>
        ) : (
          <p className={styles.mutedText}>Image generation settings are unavailable.</p>
        )}
      </CardContent>
    </Card>
  );
}
