/**
 * The WHEN card: how this automation starts.
 *
 * Triggers used to live on their own route, which put the beginning of every
 * workflow on a different screen from the steps it starts. Here they are the
 * first card, configured inline through the same declarative forms the API
 * already exposes at /triggers/forms/{type}.
 */

import { useCallback, useEffect, useState } from "react";
import { CalendarClock, ChevronDown, ChevronUp, Play, Plus, Trash2 } from "lucide-react";

import {
  Button,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  StatusBadge,
} from "../../../../components/ui";
import { SchemaForm } from "../../../../components/forms";
import { automationApiService } from "../../../../services/automations";
import type {
  AutomationTrigger,
  AutomationTriggerType,
  CreateAutomationTriggerRequest,
} from "../../../../types/automation";
import type { FormSchema, FormValue } from "../../../../types/form";
import { describeTrigger } from "../chain/actionSummary";
import type { TriggerChainItem } from "../chain/chainModel";
import { useChain } from "./chainContext";

/** Webhook triggers have no form builder or ingress route yet, so they are not offered. */
const TRIGGER_TYPES: { value: AutomationTriggerType; label: string; hint: string }[] = [
  { value: "manual", label: "Manually or from a test", hint: "You start it" },
  { value: "schedule", label: "On a schedule", hint: "Cron, in a timezone" },
];

export function TriggerCard({ item }: { item: TriggerChainItem }) {
  const { graph, readOnly, expandedNodeId, onToggleExpand, onEditTriggers } = useChain();
  const expanded = expandedNodeId === item.startNode.node_id;
  const [editing, setEditing] = useState<AutomationTrigger | "new" | null>(null);
  const [schema, setSchema] = useState<FormSchema | null>(null);
  const [triggerType, setTriggerType] = useState<AutomationTriggerType>("schedule");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const automationId = graph.automation.automation_id;
  const primary = item.triggers[0] ?? null;

  const loadSchema = useCallback(
    async (type: AutomationTriggerType) => {
      setError(null);
      try {
        setSchema(await automationApiService.getTriggerForm(automationId, type));
      } catch (loadError) {
        setSchema(null);
        setError(messageOf(loadError));
      }
    },
    [automationId]
  );

  useEffect(() => {
    if (!editing) {
      setSchema(null);
      return;
    }
    void loadSchema(triggerType);
  }, [editing, loadSchema, triggerType]);

  const openEditor = (trigger: AutomationTrigger | "new") => {
    setEditing(trigger);
    setTriggerType(trigger === "new" ? "schedule" : trigger.type);
    onToggleExpand(item.startNode.node_id);
  };

  const submit = async (values: Record<string, FormValue>) => {
    setBusy(true);
    setError(null);
    try {
      const payload = toRequest(triggerType, values, item.startNode.node_id);
      if (editing && editing !== "new") {
        await automationApiService.updateTrigger(automationId, editing.trigger_id, {
          type: payload.type,
          name: payload.name,
          enabled: payload.enabled,
          entry_node_id: payload.entry_node_id,
          config: payload.config,
        });
      } else {
        await automationApiService.createTrigger(automationId, payload);
      }
      setEditing(null);
      await onEditTriggers();
    } catch (submitError) {
      setError(messageOf(submitError));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (trigger: AutomationTrigger) => {
    setBusy(true);
    setError(null);
    try {
      await automationApiService.deleteTrigger(automationId, trigger.trigger_id);
      if (editing !== "new" && editing?.trigger_id === trigger.trigger_id) setEditing(null);
      await onEditTriggers();
    } catch (removeError) {
      setError(messageOf(removeError));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className={`chain-card chain-card--trigger ${expanded ? "chain-card--expanded" : ""}`}>
      <div className="chain-card__head">
        <span className="chain-card__gutter">WHEN</span>
        <Button
          type="button"
          variant="ghost"
          className="chain-card__summary"
          onClick={() => onToggleExpand(expanded ? null : item.startNode.node_id)}
          aria-expanded={expanded}
        >
          <span className="chain-card__icon">
            {primary?.type === "schedule" ? (
              <CalendarClock className="h-4 w-4" />
            ) : (
              <Play className="h-4 w-4" />
            )}
          </span>
          <span className="chain-card__labels">
            <strong>{primary ? describeTrigger(primary) : "No trigger yet"}</strong>
            <small>
              {item.triggers.length > 1
                ? `${item.triggers.length} triggers`
                : primary
                  ? primary.name
                  : "Choose how this automation starts"}
            </small>
          </span>
        </Button>
        <div className="chain-card__badges">
          {primary ? (
            <StatusBadge
              status={primary.enabled ? "active" : "inactive"}
              label={primary.enabled ? "on" : "off"}
            />
          ) : null}
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => onToggleExpand(expanded ? null : item.startNode.node_id)}
            aria-label={expanded ? "Collapse trigger" : "Expand trigger"}
          >
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      {expanded && (
        <div className="chain-card__body">
          {error ? <div className="chain-card__error">{error}</div> : null}

          <ul className="chain-trigger__list">
            {item.triggers.map((trigger) => (
              <li key={trigger.trigger_id}>
                <Button
                  type="button"
                  variant="ghost"
                  className="chain-trigger__row"
                  onClick={() => openEditor(trigger)}
                >
                  <span className="chain-trigger__row-icon">
                    {trigger.type === "schedule" ? (
                      <CalendarClock className="h-4 w-4" />
                    ) : (
                      <Play className="h-4 w-4" />
                    )}
                  </span>
                  <span className="chain-trigger__row-text">
                    <strong>{trigger.name}</strong>
                    <small>{describeTrigger(trigger)}</small>
                  </span>
                </Button>
                <StatusBadge
                  status={trigger.enabled ? "active" : "inactive"}
                  label={trigger.enabled ? "enabled" : "disabled"}
                />
                {!readOnly && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    disabled={busy}
                    onClick={() => void remove(trigger)}
                    aria-label={`Delete ${trigger.name}`}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                )}
              </li>
            ))}
            {item.triggers.length === 0 && (
              <li className="chain-trigger__empty">
                Nothing starts this automation yet.
              </li>
            )}
          </ul>

          {!readOnly && !editing && (
            <Button variant="outline" size="sm" onClick={() => openEditor("new")}>
              <Plus className="h-4 w-4" />
              Add a trigger
            </Button>
          )}

          {editing && (
            <div className="chain-trigger__editor">
              <div className="chain-field">
                <Select
                  value={triggerType}
                  onValueChange={(value) => setTriggerType(value as AutomationTriggerType)}
                  disabled={busy || editing !== "new"}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TRIGGER_TYPES.map((type) => (
                      <SelectItem key={type.value} value={type.value}>
                        {type.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {schema ? (
                <SchemaForm
                  key={`${editing === "new" ? "new" : editing.trigger_id}:${triggerType}`}
                  schema={schema}
                  initialValues={editing === "new" ? undefined : initialValues(editing)}
                  submitLabel={editing === "new" ? "Add trigger" : "Save trigger"}
                  cancelLabel="Cancel"
                  isLoading={busy}
                  onCancel={() => setEditing(null)}
                  onSubmit={submit}
                />
              ) : (
                <p className="chain-field__hint">Loading trigger options…</p>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function initialValues(trigger: AutomationTrigger): Record<string, FormValue> {
  return {
    name: trigger.name,
    enabled: String(trigger.enabled),
    entry_node_id: trigger.entry_node_id,
    cron_expression: String(trigger.config.cron_expression ?? ""),
    timezone: String(trigger.config.timezone ?? "UTC"),
    input: asStringMap(trigger.config.input),
  };
}

function toRequest(
  type: AutomationTriggerType,
  values: Record<string, FormValue>,
  startNodeId: string
): CreateAutomationTriggerRequest {
  const base = {
    type,
    name: text(values.name) || (type === "schedule" ? "Schedule" : "Manual"),
    enabled: String(values.enabled ?? "true") === "true",
    // Single-start graphs no longer ask for an entry step, so supply it here.
    entry_node_id: text(values.entry_node_id) || startNodeId,
  };
  if (type === "schedule") {
    return {
      ...base,
      config: {
        cron_expression: text(values.cron_expression),
        timezone: text(values.timezone) || "UTC",
        input: asStringMap(values.input),
      },
    };
  }
  return { ...base, config: {} };
}

function text(value: FormValue | undefined): string {
  return typeof value === "string" ? value : "";
}

function asStringMap(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).map(([key, item]) => [key, String(item)])
  );
}

function messageOf(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "Could not save the trigger.";
}
