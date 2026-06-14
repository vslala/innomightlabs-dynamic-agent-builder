import { useEffect, useState } from "react";
import { Loader2, Sparkles } from "lucide-react";
import { Button } from "../ui/button";
import type { FormInput, FormValue } from "../../types/form";
import {
  smartSuggestionService,
  type SmartSuggestionSettings,
} from "../../services/smartSuggestions";

interface SmartSuggestionControlProps {
  field: FormInput;
  value: FormValue;
  formData: Record<string, FormValue>;
  onApply: (value: string) => void;
}

export function SmartSuggestionControl({
  field,
  value,
  formData,
  onApply,
}: SmartSuggestionControlProps) {
  const config = field.smart_suggestion;
  const [settings, setSettings] = useState<SmartSuggestionSettings | null>(null);
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [displayText, setDisplayText] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    smartSuggestionService
      .getSettings()
      .then((nextSettings) => {
        if (active) setSettings(nextSettings);
      })
      .catch(() => {
        if (active) setSettings(null);
      })
      .finally(() => {
        if (active) setSettingsLoaded(true);
      });
    return () => {
      active = false;
    };
  }, []);

  if (!config?.enabled) return null;

  const isConfigured = Boolean(settings?.is_configured);
  const currentValue = typeof value === "string" ? value : "";

  const handleSuggest = async () => {
    if (!query.trim() || !isConfigured) return;
    setLoading(true);
    setError(null);
    setDisplayText(null);
    try {
      const response = await smartSuggestionService.suggest({
        suggestion_type: config.suggestion_type,
        query: query.trim(),
        current_value: currentValue,
        context: buildSuggestionContext(formData),
      });
      onApply(response.value);
      setDisplayText(response.display_text || null);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const handleConfigure = () => {
    window.location.href = "/dashboard/settings";
  };

  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-white/5 p-3">
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={config.prompt_placeholder || `Describe ${field.label.toLowerCase()}`}
          disabled={!settingsLoaded || !isConfigured || loading}
          className="h-9 min-w-0 flex-1 rounded-md border border-[var(--border-subtle)] bg-transparent px-3 text-sm text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--gradient-start)]"
        />
        {isConfigured ? (
          <Button
            type="button"
            size="sm"
            onClick={handleSuggest}
            disabled={!query.trim() || loading}
            className="w-full shrink-0 sm:w-auto sm:min-w-28"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            {config.button_label || "Suggest"}
          </Button>
        ) : (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={handleConfigure}
            disabled={!settingsLoaded}
            className="w-full shrink-0 sm:w-auto"
          >
            Configure model first
          </Button>
        )}
      </div>
      {displayText && (
        <p className="mt-2 text-xs leading-5 text-[var(--text-muted)]">{displayText}</p>
      )}
      {error && (
        <p className="mt-2 text-xs leading-5 text-red-400">{error}</p>
      )}
    </div>
  );
}

function buildSuggestionContext(formData: Record<string, FormValue>): Record<string, unknown> {
  const context: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(formData)) {
    if (typeof value === "string") {
      context[key] = value;
    }
  }
  return context;
}

function getErrorMessage(err: unknown): string {
  if (err instanceof Error && err.message) {
    return err.message;
  }
  return "Could not generate a suggestion.";
}
