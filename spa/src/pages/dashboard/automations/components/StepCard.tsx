/**
 * A THEN card: one action, collapsed to a summary and expanded in place.
 *
 * Expanded, the card holds everything needed to finish the step -- identity,
 * the action's own schema form, and the data from the selected run -- so
 * configuring a step never means leaving the chain.
 */

import { useMemo, useState } from "react";
import {
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  GitBranch,
  MoreHorizontal,
  Trash2,
} from "lucide-react";

import { Button, Input, Label, Textarea } from "../../../../components/ui";
import { SchemaForm, SmartValueProvider } from "../../../../components/forms";
import { automationApiService } from "../../../../services/automations";
import type { AutomationNode } from "../../../../types/automation";
import type { FormValue } from "../../../../types/form";
import { describeStep, findCatalogItem, skillActionOf } from "../chain/actionSummary";
import { aliasError, slugifyAliasInput } from "../chain/aliases";
import { canMoveStep } from "../chain/chainOperations";
import {
  actionFormFor,
  argumentsToFormValues,
  formValuesToArguments,
} from "../chain/formArguments";
import { buildSmartValueGroups } from "../chain/smartValues";
import { AutomationJsonEditor } from "./AutomationJsonEditor";
import { useChain } from "./chainContext";
import { RunStatusBadge } from "./RunStatusBadge";
import { StepDataPanel } from "./StepDataPanel";
import { StepIcon } from "./StepIcon";

export function StepCard({ node }: { node: AutomationNode }) {
  const chain = useChain();
  const {
    catalog,
    expandedNodeId,
    graph,
    issuesByNode,
    onConfigureAction,
    onConvertType,
    onDeleteStep,
    onMoveStep,
    onPatchNode,
    onToggleExpand,
    readOnly,
    resultsByNodeId,
    runContext,
  } = chain;

  const expanded = expandedNodeId === node.node_id;
  const summary = describeStep(node, catalog);
  const issues = issuesByNode.get(node.node_id) ?? [];
  const result = resultsByNodeId.get(node.node_id) ?? null;
  const item = findCatalogItem(node, catalog);
  const config = skillActionOf(node);
  const [menuOpen, setMenuOpen] = useState(false);
  // Held locally only while being typed, so a reserved name can be reported
  // without persisting a value the backend would reject.
  const [aliasDraft, setAliasDraft] = useState<string | null>(null);
  const aliasValue = aliasDraft ?? node.alias ?? "";
  const aliasProblem = aliasError(aliasValue);

  const smartValueGroups = useMemo(
    () =>
      buildSmartValueGroups({
        graph,
        forNodeId: node.node_id,
        catalog,
        context: runContext,
      }),
    [catalog, graph, node.node_id, runContext]
  );

  const preview = useMemo(
    () => async (template: string) => {
      const response = await automationApiService.previewSmartValues(
        graph.automation.automation_id,
        { template }
      );
      return response.rendered;
    },
    [graph.automation.automation_id]
  );

  const needsSetup = Boolean(item && !item.available && item.install_schema);
  // Memoised because SchemaForm keys its own state off this object; rebuilding
  // it on every render would make the form re-hydrate its options each time.
  const actionForm = useMemo(() => (item ? actionFormFor(item) : null), [item]);

  return (
    <section
      className={[
        "chain-card",
        "chain-card--step",
        expanded ? "chain-card--expanded" : "",
        issues.length > 0 ? "chain-card--flagged" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <div className="chain-card__head">
        <span className="chain-card__gutter">THEN</span>
        <Button
          type="button"
          variant="ghost"
          className="chain-card__summary"
          onClick={() => onToggleExpand(expanded ? null : node.node_id)}
          aria-expanded={expanded}
        >
          <span className="chain-card__icon">
            <StepIcon kind={summary.icon} />
          </span>
          <span className="chain-card__labels">
            <strong>{summary.title}</strong>
            {summary.subtitle ? <small>{summary.subtitle}</small> : null}
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
            aria-label={expanded ? "Collapse step" : "Expand step"}
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
                aria-label="Step actions"
              >
                <MoreHorizontal className="h-4 w-4" />
              </Button>
              {menuOpen && (
                <div className="chain-card__menu-items" role="menu">
                  <Button
                    variant="ghost"
                    className="chain-card__menu-item"
                    disabled={!canMoveStep(graph, node.node_id, "up")}
                    onClick={() => {
                      setMenuOpen(false);
                      onMoveStep(node.node_id, "up");
                    }}
                  >
                    <ChevronUp className="h-4 w-4" />
                    Move up
                  </Button>
                  <Button
                    variant="ghost"
                    className="chain-card__menu-item"
                    disabled={!canMoveStep(graph, node.node_id, "down")}
                    onClick={() => {
                      setMenuOpen(false);
                      onMoveStep(node.node_id, "down");
                    }}
                  >
                    <ChevronDown className="h-4 w-4" />
                    Move down
                  </Button>
                  <Button
                    variant="ghost"
                    className="chain-card__menu-item"
                    onClick={() => {
                      setMenuOpen(false);
                      onConvertType(node.node_id, "condition");
                    }}
                  >
                    <GitBranch className="h-4 w-4" />
                    Turn into IF / ELSE
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
                    Delete step
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {expanded && (
        <SmartValueProvider groups={smartValueGroups} preview={preview}>
          <div className="chain-card__body">
            <div className="chain-card__fields">
              <div className="chain-field">
                <Label htmlFor={`${node.node_id}-name`}>Step name</Label>
                <Input
                  id={`${node.node_id}-name`}
                  value={node.name}
                  disabled={readOnly}
                  onChange={(event) => onPatchNode(node.node_id, { name: event.target.value })}
                />
              </div>

              <div className="chain-field">
                <Label htmlFor={`${node.node_id}-alias`}>Reference name</Label>
                <Input
                  id={`${node.node_id}-alias`}
                  value={aliasValue}
                  disabled={readOnly}
                  onChange={(event) => {
                    const slug = slugifyAliasInput(event.target.value);
                    setAliasDraft(slug);
                    if (!aliasError(slug)) onPatchNode(node.node_id, { alias: slug });
                  }}
                  onBlur={() => setAliasDraft(null)}
                />
                <p className="chain-field__hint">
                  {aliasProblem ?? (
                    <>
                      Used in smart values, for example{" "}
                      <code>{`{{ steps.${node.alias || "step_name"}.output.result }}`}</code>
                    </>
                  )}
                </p>
              </div>
            </div>

            <div className="chain-field">
              <Label htmlFor={`${node.node_id}-description`}>Description</Label>
              <Textarea
                id={`${node.node_id}-description`}
                rows={2}
                value={node.description ?? ""}
                disabled={readOnly}
                placeholder="Why this step exists (optional)"
                onChange={(event) => onPatchNode(node.node_id, { description: event.target.value })}
              />
            </div>

            {!config && (
              <div className="chain-card__notice">
                This step has no action yet. Delete it, or pick one from the
                <strong> Add a step </strong>
                list.
              </div>
            )}

            {needsSetup && item && (
              <div className="chain-card__setup">
                <div>
                  <strong>{item.label} needs setup</strong>
                  <p>{item.disabled_reason}</p>
                </div>
                <Button size="sm" onClick={() => onConfigureAction(node.node_id, item)}>
                  Configure
                </Button>
              </div>
            )}

            {config && item && !needsSetup && (
              <div className="chain-card__parameters">
                {actionForm ? (
                  <SchemaForm
                    key={`${node.node_id}:${item.skill_id}:${item.action}`}
                    schema={actionForm}
                    initialValues={argumentsToFormValues(config.arguments)}
                    hideActions
                    onSubmit={() => undefined}
                    onChange={(values: Record<string, FormValue>) =>
                      onPatchNode(node.node_id, {
                        config: {
                          ...(node.config as Record<string, unknown>),
                          action_type: "skill_action",
                          installed_skill_id: item.installed_skill_id ?? null,
                          skill_id: item.skill_id,
                          action: item.action,
                          arguments: formValuesToArguments(values, item.input_schema),
                        },
                      })
                    }
                  />
                ) : (
                  <AutomationJsonEditor
                    label="Arguments"
                    value={JSON.stringify(config.arguments, null, 2)}
                    onChange={(next) => {
                      try {
                        const parsed = JSON.parse(next) as Record<string, unknown>;
                        onPatchNode(node.node_id, {
                          config: { ...(node.config as Record<string, unknown>), arguments: parsed },
                        });
                      } catch {
                        // Keep invalid drafts local to the editor until they parse.
                      }
                    }}
                  />
                )}
              </div>
            )}

            {issues.length > 0 && (
              <ul className="chain-card__issues">
                {issues.map((issue, index) => (
                  <li key={index}>{issue.message}</li>
                ))}
              </ul>
            )}

            <StepDataPanel node={node} result={result} running={chain.runInProgress} />
          </div>
        </SmartValueProvider>
      )}
    </section>
  );
}
