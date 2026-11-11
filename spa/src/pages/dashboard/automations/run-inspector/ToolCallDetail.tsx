/**
 * One move of the agent in full: which tool it called, with what, when, and everything that came back.
 * Rendered in the side pane on wide screens and in a bottom sheet on phones.
 */

import { useState, type ReactNode } from "react";

import { Button, CopyButton, JsonTreeViewer, StatusBadge, type StatusBadgeProps } from "../../../../components/ui";
import { formatClockTime, formatMs } from "../components/runStatus";
import { ExpandableText, InspectorSection, ValueList } from "./parts";
import {
  actingArguments,
  asText,
  durationMs,
  parseToolResult,
  toolCallTitle,
  type ToolCall,
} from "./toolCalls";

export function ToolCallDetail({ call, total }: { call: ToolCall; total: number }) {
  const duration = durationMs(call);

  return (
    <article className="run-inspector-call" aria-labelledby={`call-${call.id}-title`}>
      <header className="run-inspector-call__head">
        <h3 id={`call-${call.id}-title`}>
          <span className="run-inspector-call__sequence">
            {call.sequence}
            <span className="sr-only"> of {total}</span>
          </span>
          {toolCallTitle(call)}
        </h3>
        <ToolCallBadge call={call} />
      </header>

      <dl className="run-inspector-call__facts">
        <Fact label="Tool">
          <code>{call.toolName}</code>
          {call.wrapper ? <span className="run-inspector-muted"> via {call.wrapper.toolName}</span> : null}
        </Fact>
        {call.startedAt ? <Fact label="Started">{formatClockTime(call.startedAt)}</Fact> : null}
        {duration !== null ? <Fact label="Took">{formatMs(duration)}</Fact> : null}
        <Fact label="Call id">
          <code title={call.id}>{call.id}</code>
          <CopyButton value={call.id} label="Copy call id" />
        </Fact>
      </dl>

      <ArgumentsSection call={call} />
      <ResultSection call={call} />
    </article>
  );
}

export function ToolCallBadge({ call }: { call: ToolCall }) {
  const { status, label } = callBadge(call);
  return <StatusBadge status={status} label={label} />;
}

function callBadge(call: ToolCall): { status: StatusBadgeProps["status"]; label: string } {
  if (call.success === true) return { status: "success", label: "succeeded" };
  if (call.success === false) return { status: "failed", label: "failed" };
  return { status: "warning", label: "no result" };
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function ArgumentsSection({ call }: { call: ToolCall }) {
  const [asJson, setAsJson] = useState(false);
  // The JSON view is everything the model sent, wrapper included: what to compare against when debugging
  const raw = call.wrapper ? { tool: call.wrapper.toolName, arguments: call.wrapper.args } : call.args;

  return (
    <InspectorSection
      title="Arguments"
      actions={
        <>
          <JsonToggle pressed={asJson} onChange={setAsJson} />
          <CopyButton value={asText(raw)} label="Copy arguments" />
        </>
      }
    >
      {asJson ? (
        <JsonTreeViewer value={raw} maxHeight="none" />
      ) : (
        <ValueList value={actingArguments(call)} empty="Called without arguments." />
      )}
    </InspectorSection>
  );
}

function ResultSection({ call }: { call: ToolCall }) {
  const [asJson, setAsJson] = useState(false);
  const result = parseToolResult(call);

  if (result.kind === "none") {
    return (
      <InspectorSection title="Response">
        <p className="run-inspector-muted">No result was recorded: the step ended before this call returned.</p>
      </InspectorSection>
    );
  }

  const isObject = result.kind === "json" && typeof result.value === "object" && result.value !== null;
  return (
    <InspectorSection
      title="Response"
      actions={
        <>
          {isObject ? <JsonToggle pressed={asJson} onChange={setAsJson} /> : null}
          <CopyButton value={call.resultText ?? ""} label="Copy response" />
        </>
      }
    >
      {result.kind === "error" ? (
        <div className="run-inspector-error" role="alert">
          <ExpandableText text={result.message} />
        </div>
      ) : result.kind === "text" ? (
        <ExpandableText text={result.text} />
      ) : asJson || !isObject || Array.isArray(result.value) ? (
        <JsonTreeViewer value={result.value} maxHeight="none" />
      ) : (
        <ValueList value={result.value as Record<string, unknown>} empty="Returned an empty object." />
      )}
    </InspectorSection>
  );
}

function JsonToggle({ pressed, onChange }: { pressed: boolean; onChange: (pressed: boolean) => void }) {
  return (
    <Button type="button" variant="ghost" size="sm" aria-pressed={pressed} onClick={() => onChange(!pressed)}>
      {"{ } JSON"}
    </Button>
  );
}
