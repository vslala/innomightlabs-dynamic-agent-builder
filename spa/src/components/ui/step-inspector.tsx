import { useMemo, useState, type ReactNode } from "react";

import { cn } from "../../lib/utils";
import { Button } from "./button";
import { JsonTreeViewer, jsonValueSummary, normalizeJsonValue } from "./json-viewer";
import { Label } from "./label";
import styles from "./step-inspector.module.css";

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
      <section className={cn(styles.emptySection, className)}>
        <h3 className={styles.emptyTitle}>{title}</h3>
        <p className={styles.emptyMessage}>{emptyMessage}</p>
      </section>
    );
  }

  return (
    <section className={cn(styles.section, className)}>
      <div className={styles.sectionHeader}>
        <h3 className={styles.sectionTitle}>{title}</h3>
        {description && <p className={styles.sectionDescription}>{description}</p>}
      </div>

      <div className={styles.content}>
        <div
          className={styles.stepsGrid}
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
                  styles.stepButton,
                  isSelected && styles.stepButtonSelected
                )}
                style={{ padding: "var(--space-3)" }}
                onClick={() => selectStep(step.id)}
              >
                <div className={styles.stepButtonInner}>
                  <div className={styles.stepRow}>
                    <span className={styles.stepLabelGroup}>
                      <span className={styles.stepIndex}>
                        {index + 1}
                      </span>
                      <span className={styles.stepTitle}>
                        {step.title || `Step ${index + 1}`}
                      </span>
                    </span>
                    {step.status}
                  </div>
                  {step.subtitle && (
                    <span className={styles.stepSubtitle}>
                      {step.subtitle}
                    </span>
                  )}
                  <span className={styles.stepSummary}>
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
    <div className={cn(styles.detail, className)}>
      <div className={styles.detailHeader}>
        <div className={styles.detailTitleGroup}>
          <Label>{step.title}</Label>
          {step.subtitle && <p className={styles.detailSubtitle}>{step.subtitle}</p>}
        </div>
        <div className={styles.detailMetaGroup}>
          {step.meta}
          {step.status}
        </div>
      </div>

      {step.error && (
        <div className={styles.detailError}>
          {step.error}
        </div>
      )}

      <div
        className={styles.detailPanels}
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
