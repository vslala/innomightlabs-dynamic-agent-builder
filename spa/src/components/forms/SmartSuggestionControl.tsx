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
    <div className="rounded-lg border border-[var(--border-subtle)] bg-white/[0.04] p-3">
      <div className="flex flex-col gap-2 min-[420px]:flex-row">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={config.prompt_placeholder || `Describe ${field.label.toLowerCase()}`}
          disabled={!settingsLoaded || !isConfigured || loading}
          className="h-10 min-w-0 flex-1 rounded-md border border-[var(--border-subtle)] bg-transparent px-3.5 py-2 text-sm leading-5 text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--gradient-start)]"
          style={{
            paddingInline: "0.875rem",
            paddingBlock: "0.5rem",
            boxSizing: "border-box",
          }}
        />
        {isConfigured ? (
          <Button
            type="button"
            size="sm"
            onClick={handleSuggest}
            disabled={!query.trim() || loading}
            className="h-10 w-full shrink-0 px-3 min-[420px]:w-auto min-[420px]:min-w-28"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            <span className="truncate">{config.button_label || "Suggest"}</span>
          </Button>
        ) : (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={handleConfigure}
            disabled={!settingsLoaded}
            className="h-10 w-full shrink-0 px-3 min-[420px]:w-auto"
          >
            <span className="truncate">Configure model first</span>
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
