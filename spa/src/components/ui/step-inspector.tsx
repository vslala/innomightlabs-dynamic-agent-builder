import { useMemo, useState, type ReactNode } from "react";

import { cn } from "../../lib/utils";
import { Button } from "./button";
import { JsonTreeViewer, jsonValueSummary, normalizeJsonValue } from "./json-viewer";
import { Label } from "./label";

export interface StepInspectorItem {
  id: string;
  title: string;
  subtitle?: string;
  input?: unknown;
  output?: unknown;
  error?: string | null;
  status?: ReactNode;
  meta?: ReactNode;
  detailPanels?: ReactNode;
}

interface StepInspectorProps {
  title?: string;
  description?: string;
  steps: StepInspectorItem[];
  emptyMessage?: string;
  defaultStepId?: string;
  selectedStepId?: string | null;
  onSelectedStepChange?: (stepId: string) => void;
  showDetails?: boolean;
  className?: string;
}

export function StepInspector({
  title = "Step inspector",
  description = "Select a step to inspect its input and output.",
  steps,
  emptyMessage = "No step results are available.",
  defaultStepId,
  selectedStepId: controlledSelectedStepId,
  onSelectedStepChange,
  showDetails = true,
  className,
}: StepInspectorProps) {
  const [uncontrolledSelectedStepId, setUncontrolledSelectedStepId] = useState<string | null>(
    defaultStepId ?? steps[0]?.id ?? null
  );
  const selectedStepId = controlledSelectedStepId ?? uncontrolledSelectedStepId;
  const selectedStep = useMemo(
    () => steps.find((step) => step.id === selectedStepId) ?? steps[0] ?? null,
    [selectedStepId, steps]
  );
  const selectStep = (stepId: string) => {
    setUncontrolledSelectedStepId(stepId);
    onSelectedStepChange?.(stepId);
  };

  if (steps.length === 0) {
    return (
      <section className={cn("rounded-lg border border-[var(--border-subtle)] p-4", className)}>
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h3>
        <p className="mt-2 text-sm text-[var(--text-muted)]">{emptyMessage}</p>
      </section>
    );
  }

  return (
    <section className={cn("grid min-w-0 gap-4", className)}>
      <div className="grid gap-1">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h3>
        {description && <p className="text-sm text-[var(--text-muted)]">{description}</p>}
      </div>

      <div className="grid min-w-0 gap-4">
        <div
          className="grid content-start gap-3"
          style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(13rem, 100%), 1fr))" }}
        >
          {steps.map((step, index) => {
            const isSelected = selectedStep?.id === step.id;
            return (
              <Button
                key={step.id}
                type="button"
                variant={isSelected ? "secondary" : "outline"}
                className={cn(
                  "h-auto w-full min-w-0 justify-start whitespace-normal rounded-lg text-left",
                  isSelected && "border-[var(--gradient-start)] bg-[var(--bg-tertiary)]"
                )}
                style={{ padding: "var(--space-3)" }}
                onClick={() => selectStep(step.id)}
              >
                <div className="grid min-w-0 flex-1 gap-2">
                  <div className="flex min-w-0 items-start justify-between gap-3">
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--bg-tertiary)] text-xs font-semibold text-[var(--text-primary)]">
                        {index + 1}
                      </span>
                      <span className="min-w-0 truncate text-sm font-semibold text-[var(--text-primary)]">
                        {step.title || `Step ${index + 1}`}
                      </span>
                    </span>
                    {step.status}
                  </div>
                  {step.subtitle && (
                    <span className="min-w-0 break-all text-xs text-[var(--text-muted)]">
                      {step.subtitle}
                    </span>
                  )}
                  <span className="text-xs text-[var(--text-muted)]">
                    Input {summarize(step.input)} · Output {summarize(step.output)}
                  </span>
                </div>
              </Button>
            );
          })}
        </div>

        {showDetails && selectedStep && <StepInspectorDetail step={selectedStep} />}
      </div>
    </section>
  );
}

export function StepInspectorDetail({ step, className }: { step: StepInspectorItem; className?: string }) {
  return (
    <div className={cn("grid min-w-0 gap-4 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-4", className)}>
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Label>{step.title}</Label>
          {step.subtitle && <p className="mt-1 break-all text-xs text-[var(--text-muted)]">{step.subtitle}</p>}
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {step.meta}
          {step.status}
        </div>
      </div>

      {step.error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
          {step.error}
        </div>
      )}

      <div
        className="grid min-w-0 gap-5"
        style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(28rem, 100%), 1fr))" }}
      >
        <JsonTreeViewer label="Input" value={step.input ?? {}} maxHeight="36rem" />
        <JsonTreeViewer label="Output" value={step.output ?? {}} maxHeight="36rem" />
        {step.detailPanels}
      </div>
    </div>
  );
}

function summarize(value: unknown): string {
  const normalized = normalizeJsonValue(value);
  return typeof normalized === "string" ? "text" : jsonValueSummary(normalized);
}
