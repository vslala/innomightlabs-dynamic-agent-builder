/**
 * An IF card and the two lanes it opens.
 *
 * The lanes are the only branching the chain expresses, and the editor keeps
 * them well formed: both always lead somewhere, so no branch can dead-end.
 */

import { useMemo, useState } from "react";
import {
  AlertTriangle,
  Ban,
  ChevronDown,
  ChevronUp,
  GitBranch,
  MoreHorizontal,
  Trash2,
  Zap,
} from "lucide-react";

import { Button, Input, Label } from "../../../../components/ui";
import type { ChainLane, ConditionChainItem } from "../chain/chainModel";
import { describeParsedCondition } from "../chain/conditionExpression";
import { buildSmartValueGroups } from "../chain/smartValues";
import { ChainColumn } from "./ChainColumn";
import { useChain } from "./chainContext";
import { ConditionBuilder } from "./ConditionBuilder";
import { InsertAffordance } from "./InsertAffordance";
import { RunStatusBadge } from "./RunStatusBadge";
import { StepDataPanel } from "./StepDataPanel";

export function ConditionCard({ item }: { item: ConditionChainItem }) {
  const {
    catalog,
    expandedNodeId,
    graph,
    issuesByNode,
    onConvertType,
    onDeleteStep,
    onPatchNode,
    onToggleExpand,
    readOnly,
    resultsByNodeId,
    runContext,
    runInProgress,
  } = useChain();

  const node = item.node;
  const expanded = expandedNodeId === node.node_id;
  const issues = issuesByNode.get(node.node_id) ?? [];
  const result = resultsByNodeId.get(node.node_id) ?? null;
  const [menuOpen, setMenuOpen] = useState(false);

  const expression = typeof node.config.expression === "string" ? node.config.expression : "";
  const summary = describeParsedCondition(expression) ?? "No condition set";

  const groups = useMemo(
    () => buildSmartValueGroups({ graph, forNodeId: node.node_id, catalog, context: runContext }),
    [catalog, graph, node.node_id, runContext]
  );

  const setExpression = (next: string) =>
    onPatchNode(node.node_id, {
      config: {
        ...(node.config as Record<string, unknown>),
        expression: next,
        true_label: "true",
        false_label: "false",
      },
    });

  return (
    <>
      <section
        className={[
          "chain-card",
          "chain-card--condition",
          expanded ? "chain-card--expanded" : "",
          issues.length > 0 ? "chain-card--flagged" : "",
        ]
          .filter(Boolean)
          .join(" ")}
      >
        <div className="chain-card__head">
          <span className="chain-card__gutter">IF</span>
          <Button
            type="button"
            variant="ghost"
            className="chain-card__summary"
            onClick={() => onToggleExpand(expanded ? null : node.node_id)}
            aria-expanded={expanded}
          >
            <span className="chain-card__icon">
              <GitBranch className="h-4 w-4" />
            </span>
            <span className="chain-card__labels">
              <strong>{node.name || "Condition"}</strong>
              <small>{summary}</small>
            </span>
          </Button>

          <div className="chain-card__badges">
            {issues.length > 0 && (
              <span className="chain-card__issue" title={issues.map((issue) => issue.message).join("\n")}>
                <AlertTriangle className="h-3.5 w-3.5" />
              </span>
            )}
            {result ? <RunStatusBadge status={result.status} /> : null}
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => onToggleExpand(expanded ? null : node.node_id)}
              aria-label={expanded ? "Collapse condition" : "Expand condition"}
            >
              {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </Button>
            {!readOnly && (
              <div className="chain-card__menu">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => setMenuOpen((open) => !open)}
                  aria-label="Condition actions"
                >
                  <MoreHorizontal className="h-4 w-4" />
                </Button>
                {menuOpen && (
                  <div className="chain-card__menu-items" role="menu">
                    <Button
                      variant="ghost"
                      className="chain-card__menu-item"
                      onClick={() => {
                        setMenuOpen(false);
                        onConvertType(node.node_id, "action");
                      }}
                    >
                      <Zap className="h-4 w-4" />
                      Turn into an action
                    </Button>
                    <Button
                      variant="ghost"
                      className="chain-card__menu-item chain-card__menu-item--danger"
                      onClick={() => {
                        setMenuOpen(false);
                        onDeleteStep(node.node_id);
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                      Delete condition
                    </Button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {expanded && (
          <div className="chain-card__body">
            <div className="chain-field">
              <Label htmlFor={`${node.node_id}-name`}>Step name</Label>
              <Input
                id={`${node.node_id}-name`}
                value={node.name}
                disabled={readOnly}
                onChange={(event) => onPatchNode(node.node_id, { name: event.target.value })}
              />
            </div>

            <ConditionBuilder
              expression={expression}
              groups={groups}
              disabled={readOnly}
              onChange={setExpression}
            />

            {issues.length > 0 && (
              <ul className="chain-card__issues">
                {issues.map((issue, index) => (
                  <li key={index}>{issue.message}</li>
                ))}
              </ul>
            )}

            <StepDataPanel node={node} result={result} running={runInProgress} />
          </div>
        )}
      </section>

      <div className="chain-lanes">
        {item.lanes.map((lane) => (
          <BranchLane key={lane.label} conditionNodeId={node.node_id} lane={lane} />
        ))}
      </div>
    </>
  );
}

function BranchLane({
  conditionNodeId,
  lane,
}: {
  conditionNodeId: string;
  lane: ChainLane;
}) {
  const { onOpenPalette, onStopLane, readOnly } = useChain();

  return (
    <div className={`chain-lane chain-lane--${lane.label}`}>
      <div className="chain-lane__label">
        <span>{lane.label === "true" ? "then" : "otherwise"}</span>
      </div>

      <div className="chain-lane__body">
        {lane.stops ? (
          <div className="chain-card chain-card--stop">
            <span className="chain-card__icon">
              <Ban className="h-4 w-4" />
            </span>
            <span className="chain-card__labels">
              <strong>Stop</strong>
              <small>Nothing else runs on this branch</small>
            </span>
            <InsertAffordance
              edgeId={lane.edgeId}
              onOpenPalette={onOpenPalette}
              disabled={readOnly}
              label="Add a step to this branch"
            />
          </div>
        ) : (
          <>
            {/* The first lane item carries the lane edge, so ChainColumn renders
                that insert point itself. */}
            <ChainColumn items={lane.items} />
            {!readOnly && lane.items.length > 0 && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="chain-lane__stop"
                onClick={() => onStopLane(conditionNodeId, lane.label)}
              >
                <Ban className="h-3.5 w-3.5" />
                Stop here instead
              </Button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
