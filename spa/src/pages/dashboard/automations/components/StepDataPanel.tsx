/**
 * The data half of a step card: what this step received and produced.
 *
 * This is the point of the redesign. Parameters and the real values flowing
 * through the step are on screen together, and every leaf of the output can be
 * inserted into the parameter field the user last touched -- so referencing a
 * previous step never requires copying an id from another screen.
 */

import { useState } from "react";
import { CornerDownLeft, Loader2 } from "lucide-react";

import {
  AccordionPanel,
  Button,
  JsonTreeViewer,
  StatusBadge,
} from "../../../../components/ui";
import { useOptionalSmartValues } from "../../../../components/forms";
import type { AutomationNode, AutomationRunNodeResult } from "../../../../types/automation";
import { getLifecycleEvents, getRuntimeLogSteps, getToolCalls } from "../runDisplay";
import { stepReference } from "../chain/smartValues";
import { RunStatusBadge } from "./RunStatusBadge";
import { formatDuration, formatRelativeTime } from "./runStatus";

const MAX_TREE_DEPTH = 6;

export function StepDataPanel({
  node,
  result,
  running,
}: {
  node: AutomationNode;
  result: AutomationRunNodeResult | null;
  running: boolean;
}) {
  if (!result) {
    return (
      <div className="chain-data chain-data--empty">
        {running ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>Waiting for this step to run…</span>
          </>
        ) : (
          <span>
            Run a test to see what this step receives and returns. Output values can then be
            inserted straight into the fields above.
          </span>
        )}
      </div>
    );
  }

  const events = getRuntimeLogSteps([result])[0]?.events ?? [];
  const toolCalls = getToolCalls(events);
  const lifecycle = getLifecycleEvents(events);
  const duration = formatDuration(result.started_at, result.completed_at);
  const base = `${stepReference(node)}.output`;

  return (
    <div className="chain-data">
      <div className="chain-data__header">
        <RunStatusBadge status={result.status} />
        <span>{formatRelativeTime(result.started_at)}</span>
        {duration ? <span>· {duration}</span> : null}
      </div>

      {result.error ? <div className="chain-data__error">{result.error}</div> : null}

      <div className="chain-data__grid">
        <section className="chain-data__panel">
          <h5>Input</h5>
          <JsonTreeViewer value={result.input ?? {}} maxHeight="18rem" />
        </section>

        <section className="chain-data__panel">
          <h5>Output</h5>
          <OutputTree value={result.output ?? {}} basePath={base} />
        </section>
      </div>

      {lifecycle.length > 0 && (
        <AccordionPanel
          title={<span className="chain-data__accordion-title">Lifecycle</span>}
          subtitle={`${lifecycle.length} event${lifecycle.length === 1 ? "" : "s"}`}
        >
          <ol className="automation-runtime-events__list">
            {lifecycle.map((event, index) => (
              <li key={`${event.event_type}-${index}`} className="automation-runtime-events__list-item">
                <span>{index + 1}</span>
                <p>{event.content || event.event_type}</p>
              </li>
            ))}
          </ol>
        </AccordionPanel>
      )}

      {toolCalls.length > 0 && (
        <AccordionPanel
          title={<span className="chain-data__accordion-title">Tool calls</span>}
          subtitle={`${toolCalls.length} call${toolCalls.length === 1 ? "" : "s"}`}
        >
          <div className="automation-runtime-events__accordions">
            {toolCalls.map((call, index) => (
              <AccordionPanel
                key={call.id}
                defaultOpen={index === 0}
                title={<span className="chain-data__accordion-title">{call.title}</span>}
                subtitle={call.subtitle}
                trailing={
                  call.success === null ? (
                    <StatusBadge status="info" label="started" />
                  ) : (
                    <StatusBadge
                      status={call.success ? "success" : "failed"}
                      label={call.success ? "success" : "failed"}
                    />
                  )
                }
              >
                <div className="grid min-w-0 gap-4">
                  {call.args ? <JsonTreeViewer label="Arguments" value={call.args} maxHeight="14rem" /> : null}
                  <JsonTreeViewer label="Tool response" value={call.result} maxHeight="18rem" />
                </div>
              </AccordionPanel>
            ))}
          </div>
        </AccordionPanel>
      )}
    </div>
  );
}

function OutputTree({ value, basePath }: { value: unknown; basePath: string }) {
  const smartValues = useOptionalSmartValues();

  const insert = (path: string) => {
    const target = smartValues?.getTarget();
    target?.insert(`{{ ${path} }}`);
  };

  return (
    <div className="chain-output-tree">
      <TreeNode
        label="output"
        value={value}
        path={basePath}
        depth={0}
        onInsert={smartValues ? insert : null}
        defaultOpen
      />
    </div>
  );
}

function TreeNode({
  label,
  value,
  path,
  depth,
  onInsert,
  defaultOpen = false,
}: {
  label: string;
  value: unknown;
  path: string;
  depth: number;
  onInsert: ((path: string) => void) | null;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen || depth < 2);
  const branch = value !== null && typeof value === "object";
  const entries: [string, unknown][] = Array.isArray(value)
    ? value.map((item, index) => [String(index), item])
    : branch
      ? Object.entries(value as Record<string, unknown>)
      : [];

  return (
    <div className="chain-output-tree__node" style={{ paddingLeft: depth === 0 ? 0 : "0.75rem" }}>
      <div className="chain-output-tree__row">
        {branch && entries.length > 0 ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="chain-output-tree__toggle"
            onClick={() => setOpen((current) => !current)}
            aria-label={open ? `Collapse ${label}` : `Expand ${label}`}
          >
            {open ? "−" : "+"}
          </Button>
        ) : (
          <span className="chain-output-tree__toggle-spacer" />
        )}

        <span className="chain-output-tree__key">{label}</span>
        <span className="chain-output-tree__value">{summarize(value)}</span>

        {onInsert && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="chain-output-tree__insert"
            title={`Insert {{ ${path} }}`}
            aria-label={`Insert ${path}`}
            onClick={() => onInsert(path)}
          >
            <CornerDownLeft className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>

      {branch && open && depth < MAX_TREE_DEPTH && (
        <div className="chain-output-tree__children">
          {entries.slice(0, 50).map(([key, item]) => (
            <TreeNode
              key={key}
              label={key}
              value={item}
              path={`${path}.${key}`}
              depth={depth + 1}
              onInsert={onInsert}
            />
          ))}
          {entries.length > 50 ? (
            <p className="chain-output-tree__truncated">
              {entries.length - 50} more not shown
            </p>
          ) : null}
        </div>
      )}
    </div>
  );
}

function summarize(value: unknown): string {
  if (value === null) return "null";
  if (value === undefined) return "";
  if (Array.isArray(value)) return `[${value.length}]`;
  if (typeof value === "object") return `{${Object.keys(value as Record<string, unknown>).length}}`;
  const text = String(value).replace(/\s+/g, " ").trim();
  return text.length > 80 ? `${text.slice(0, 80)}…` : text;
}
