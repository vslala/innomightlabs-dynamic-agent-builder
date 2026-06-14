import { useCallback, useEffect, useMemo, useState } from "react";
import { CalendarClock, Play, Plus, Trash2 } from "lucide-react";
import { useOutletContext, useParams } from "react-router-dom";

import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { SchemaForm } from "../../../components/forms/SchemaForm";
import { automationApiService } from "../../../services/automations";
import type {
  AutomationResponse,
  AutomationTrigger,
  AutomationTriggerType,
  CreateAutomationTriggerRequest,
  UpdateAutomationTriggerRequest,
} from "../../../types/automation";
import type { FormSchema, FormValue } from "../../../types/form";

interface OutletContext {
  automation: AutomationResponse;
  reloadAutomation: () => Promise<void>;
}

type EditorMode = "create" | "edit";

interface EditorState {
  mode: EditorMode;
  triggerType: AutomationTriggerType;
  trigger?: AutomationTrigger;
}

function boolValue(value: FormValue): boolean {
  return String(value) === "true";
}

function textValue(value: FormValue, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function objectValue(value: FormValue): Record<string, string> {
  if (value && typeof value === "object" && !(value instanceof FileList) && !Array.isArray(value)) {
    return value;
  }
  return {};
}

function inputConfigValue(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [key, String(item)])
  );
}

function valuesToTriggerRequest(
  triggerType: AutomationTriggerType,
  values: Record<string, FormValue>
): CreateAutomationTriggerRequest {
  const base = {
    type: triggerType,
    name: textValue(values.name),
    enabled: boolValue(values.enabled),
    entry_node_id: textValue(values.entry_node_id),
  };
  if (triggerType === "schedule") {
    return {
      ...base,
      config: {
        cron_expression: textValue(values.cron_expression),
        timezone: textValue(values.timezone, "UTC") || "UTC",
        input: objectValue(values.input),
      },
    };
  }
  return { ...base, config: {} };
}

function triggerToInitialValues(trigger: AutomationTrigger): Record<string, FormValue> {
  return {
    name: trigger.name,
    enabled: String(trigger.enabled),
    entry_node_id: trigger.entry_node_id,
    cron_expression: String(trigger.config.cron_expression ?? ""),
    timezone: String(trigger.config.timezone ?? "UTC"),
    input: inputConfigValue(trigger.config.input),
  };
}

function triggerIcon(type: AutomationTriggerType) {
  return type === "schedule" ? CalendarClock : Play;
}

export function AutomationTriggersPage() {
  const { automationId } = useParams<{ automationId: string }>();
  const { automation } = useOutletContext<OutletContext>();
  const [triggers, setTriggers] = useState<AutomationTrigger[]>([]);
  const [schema, setSchema] = useState<FormSchema | null>(null);
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedInitialValues = useMemo(() => {
    return editor?.trigger ? triggerToInitialValues(editor.trigger) : undefined;
  }, [editor]);

  const loadTriggers = useCallback(async () => {
    if (!automationId) return;
    setLoading(true);
    setError(null);
    try {
      setTriggers(await automationApiService.listTriggers(automationId));
    } catch (err) {
      console.error("Failed to load triggers:", err);
      setError("Failed to load triggers.");
    } finally {
      setLoading(false);
    }
  }, [automationId]);

  const openEditor = useCallback(
    async (nextEditor: EditorState) => {
      if (!automationId) return;
      setError(null);
      setEditor(nextEditor);
      try {
        setSchema(await automationApiService.getTriggerForm(automationId, nextEditor.triggerType));
      } catch (err) {
        console.error("Failed to load trigger form:", err);
        setError("Failed to load trigger form.");
        setEditor(null);
        setSchema(null);
      }
    },
    [automationId]
  );

  useEffect(() => {
    void loadTriggers();
  }, [loadTriggers]);

  const handleSubmit = async (values: Record<string, FormValue>) => {
    if (!automationId || !editor) return;
    setSaving(true);
    setError(null);
    try {
      const payload = valuesToTriggerRequest(editor.triggerType, values);
      if (editor.mode === "edit" && editor.trigger) {
        const updatePayload: UpdateAutomationTriggerRequest = {
          name: payload.name,
          enabled: payload.enabled,
          entry_node_id: payload.entry_node_id,
          config: payload.config,
        };
        await automationApiService.updateTrigger(automationId, editor.trigger.trigger_id, updatePayload);
      } else {
        await automationApiService.createTrigger(automationId, payload);
      }
      setEditor(null);
      setSchema(null);
      await loadTriggers();
    } catch (err) {
      console.error("Failed to save trigger:", err);
      setError("Failed to save trigger.");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (trigger: AutomationTrigger) => {
    if (!automationId) return;
    setSaving(true);
    setError(null);
    try {
      await automationApiService.deleteTrigger(automationId, trigger.trigger_id);
      if (editor?.trigger?.trigger_id === trigger.trigger_id) {
        setEditor(null);
        setSchema(null);
      }
      await loadTriggers();
    } catch (err) {
      console.error("Failed to delete trigger:", err);
      setError("Failed to delete trigger.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">Triggers</h2>
          <p className="text-sm text-[var(--text-muted)]">
            Start {automation.title} manually or on a schedule.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => openEditor({ mode: "create", triggerType: "manual" })}>
            <Play />
            Manual
          </Button>
          <Button onClick={() => openEditor({ mode: "create", triggerType: "schedule" })}>
            <Plus />
            Schedule
          </Button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_24rem]">
        <div className="flex min-w-0 flex-col gap-4">
          {loading ? (
            <div className="h-24 rounded-lg border border-[var(--border-subtle)] bg-white/5" />
          ) : triggers.length === 0 ? (
            <div className="rounded-lg border border-dashed border-[var(--border-subtle)] bg-white/5 p-8 text-center text-sm text-[var(--text-muted)]">
              No triggers configured.
            </div>
          ) : (
            triggers.map((trigger) => {
              const Icon = triggerIcon(trigger.type);
              return (
                <Card key={trigger.trigger_id} className="transition-colors hover:bg-white/[0.04]">
                  <CardContent className="flex items-center justify-between gap-4 p-4">
                    <button
                      type="button"
                      className="flex min-w-0 flex-1 items-center gap-3 rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--gradient-start)]/50"
                      onClick={() => openEditor({ mode: "edit", triggerType: trigger.type, trigger })}
                    >
                      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-white/5 text-[var(--text-secondary)]">
                        <Icon className="h-4 w-4" />
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium text-[var(--text-primary)]">
                          {trigger.name}
                        </span>
                        <span className="block truncate text-xs text-[var(--text-muted)]">
                          {trigger.type}
                          {trigger.type === "schedule" && trigger.config.cron_expression
                            ? ` · ${String(trigger.config.cron_expression)}`
                            : ""}
                        </span>
                      </span>
                    </button>
                    <span className={trigger.enabled ? "text-xs text-emerald-300" : "text-xs text-[var(--text-muted)]"}>
                      {trigger.enabled ? "enabled" : "disabled"}
                    </span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      disabled={saving}
                      onClick={() => handleDelete(trigger)}
                    >
                      <Trash2 />
                    </Button>
                  </CardContent>
                </Card>
              );
            })
          )}
        </div>

        <Card>
          <CardHeader>
            <CardTitle>{editor?.mode === "edit" ? "Edit trigger" : "Add trigger"}</CardTitle>
          </CardHeader>
          <CardContent>
            {editor && schema ? (
              <SchemaForm
                schema={schema}
                initialValues={selectedInitialValues}
                submitLabel={editor.mode === "edit" ? "Save trigger" : "Create trigger"}
                cancelLabel="Cancel"
                isLoading={saving}
                onCancel={() => {
                  setEditor(null);
                  setSchema(null);
                }}
                onSubmit={handleSubmit}
              />
            ) : (
              <p className="text-sm text-[var(--text-muted)]">
                Choose Manual or Schedule to configure how this automation starts.
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
