/**
 * What still needs fixing, in one place.
 *
 * Client checks give the per-step list; the backend message from a failed
 * activation or test run is shown verbatim, because it is the authoritative one.
 */

import { AlertTriangle, X } from "lucide-react";

import { Button } from "../../../../components/ui";
import type { AutomationGraphResponse } from "../../../../types/automation";
import type { ChainIssue } from "../chain/chainValidation";

export function IssuesPanel({
  issues,
  serverError,
  graph,
  onClose,
  onSelectStep,
}: {
  issues: ChainIssue[];
  serverError: string | null;
  graph: AutomationGraphResponse;
  onClose: () => void;
  onSelectStep: (nodeId: string) => void;
}) {
  const nameOf = (nodeId: string | null) =>
    graph.nodes.find((node) => node.node_id === nodeId)?.name ?? "Workflow";

  return (
    <aside className="automation-issues">
      <div className="automation-issues__head">
        <h3>
          <AlertTriangle className="h-4 w-4" />
          Needs attention
        </h3>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close issues">
          <X className="h-4 w-4" />
        </Button>
      </div>

      {serverError ? (
        <div className="automation-issues__server">
          <strong>The last activation or test run was rejected</strong>
          <p>{serverError}</p>
        </div>
      ) : null}

      {issues.length === 0 ? (
        <p className="automation-issues__empty">Nothing to fix. This workflow is ready to run.</p>
      ) : (
        <ul className="automation-issues__list">
          {issues.map((issue, index) => (
            <li key={index}>
              {issue.nodeId ? (
                <Button
                  variant="ghost"
                  className="automation-issues__item"
                  onClick={() => onSelectStep(issue.nodeId as string)}
                >
                  <span className={`automation-issues__dot automation-issues__dot--${issue.severity}`} />
                  <span>
                    <strong>{nameOf(issue.nodeId)}</strong>
                    <small>{issue.message}</small>
                  </span>
                </Button>
              ) : (
                <div className="automation-issues__item automation-issues__item--static">
                  <span className={`automation-issues__dot automation-issues__dot--${issue.severity}`} />
                  <span>
                    <strong>Workflow</strong>
                    <small>{issue.message}</small>
                  </span>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
