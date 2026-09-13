/**
 * Search-and-pick over the action catalog.
 *
 * Replaces the flat `"{skill}: {action}"` dropdown that used to be buried in the
 * inspector. Actions that need setup are offered rather than disabled: picking
 * one creates the step and shows its install form in place.
 */

import { useMemo, useState } from "react";
import { GitBranch, Ban, Settings2 } from "lucide-react";

import {
  Button,
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  SearchInput,
  StatusBadge,
} from "../../../../components/ui";
import type { AutomationActionCatalogItem } from "../../../../types/automation";
import { catalogItemKey } from "../chain/actionSummary";
import { StepIcon } from "./StepIcon";

export type PaletteChoice =
  | { kind: "action"; item: AutomationActionCatalogItem }
  | { kind: "condition" }
  | { kind: "stop" };

export function AddStepPalette({
  open,
  catalog,
  allowStop,
  onClose,
  onChoose,
}: {
  open: boolean;
  catalog: AutomationActionCatalogItem[];
  allowStop: boolean;
  onClose: () => void;
  onChoose: (choice: PaletteChoice) => void;
}) {
  // The workspace keys this component by the edge being inserted on, so each
  // open starts with a fresh query.
  const [query, setQuery] = useState("");

  const { available, needsSetup } = useMemo(() => groupCatalog(catalog, query), [catalog, query]);
  const showLogic = matches("if else condition branch", query) || !query.trim();
  const showStop = allowStop && (matches("stop end nothing", query) || !query.trim());

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : onClose())}>
      <DialogContent className="automation-palette">
        <DialogHeader>
          <DialogTitle>Add a step</DialogTitle>
          <DialogDescription>
            Pick what should happen next. Steps run in order, top to bottom.
          </DialogDescription>
        </DialogHeader>

        <SearchInput
          autoFocus
          placeholder="Search actions, skills, or logic"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />

        <DialogBody className="automation-palette__body">
          {(showLogic || showStop) && (
            <section className="automation-palette__group">
              <h4>Logic</h4>
              {showLogic && (
                <PaletteRow
                  icon={<GitBranch className="h-4 w-4" />}
                  title="IF / ELSE"
                  description="Split the workflow on a condition"
                  onSelect={() => onChoose({ kind: "condition" })}
                />
              )}
              {showStop && (
                <PaletteRow
                  icon={<Ban className="h-4 w-4" />}
                  title="Stop"
                  description="End this branch without running anything else"
                  onSelect={() => onChoose({ kind: "stop" })}
                />
              )}
            </section>
          )}

          {[...available.entries()].map(([skillName, items]) => (
            <section className="automation-palette__group" key={skillName}>
              <h4>{skillName}</h4>
              {items.map((item) => (
                <PaletteRow
                  key={catalogItemKey(item)}
                  icon={<StepIcon kind={iconFor(item)} />}
                  title={actionTitle(item)}
                  description={item.description}
                  onSelect={() => onChoose({ kind: "action", item })}
                />
              ))}
            </section>
          ))}

          {needsSetup.length > 0 && (
            <section className="automation-palette__group">
              <h4>Needs setup</h4>
              {needsSetup.map((item) => (
                <PaletteRow
                  key={catalogItemKey(item)}
                  icon={<Settings2 className="h-4 w-4" />}
                  title={item.label}
                  description={item.disabled_reason ?? item.description}
                  trailing={<StatusBadge status="warning" label="setup" />}
                  onSelect={() => onChoose({ kind: "action", item })}
                />
              ))}
            </section>
          )}

          {available.size === 0 && needsSetup.length === 0 && !showLogic && !showStop && (
            <p className="automation-palette__empty">No actions match “{query}”.</p>
          )}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}

function PaletteRow({
  icon,
  title,
  description,
  trailing,
  onSelect,
}: {
  icon: React.ReactNode;
  title: string;
  description?: string | null;
  trailing?: React.ReactNode;
  onSelect: () => void;
}) {
  return (
    <Button
      type="button"
      variant="ghost"
      className="automation-palette__row"
      onClick={onSelect}
    >
      <span className="automation-palette__row-icon">{icon}</span>
      <span className="automation-palette__row-text">
        <strong>{title}</strong>
        {description ? <small>{description}</small> : null}
      </span>
      {trailing}
    </Button>
  );
}

function groupCatalog(
  catalog: AutomationActionCatalogItem[],
  query: string
): { available: Map<string, AutomationActionCatalogItem[]>; needsSetup: AutomationActionCatalogItem[] } {
  const available = new Map<string, AutomationActionCatalogItem[]>();
  const needsSetup: AutomationActionCatalogItem[] = [];

  catalog
    .filter((item) => matches(`${item.label} ${item.skill_name} ${item.action} ${item.description}`, query))
    .forEach((item) => {
      if (!item.available) {
        needsSetup.push(item);
        return;
      }
      const list = available.get(item.skill_name);
      if (list) list.push(item);
      else available.set(item.skill_name, [item]);
    });

  return { available, needsSetup };
}

function matches(haystack: string, query: string): boolean {
  const trimmed = query.trim().toLowerCase();
  if (!trimmed) return true;
  const text = haystack.toLowerCase();
  return trimmed.split(/\s+/).every((term) => text.includes(term));
}

/** The catalog label repeats the skill name, which is already the group heading. */
function actionTitle(item: AutomationActionCatalogItem): string {
  const prefix = `${item.skill_name}: `;
  return item.label.startsWith(prefix) ? item.label.slice(prefix.length) : item.label;
}

function iconFor(item: AutomationActionCatalogItem) {
  if (item.skill_id === "agent_invocation") return "agent" as const;
  if (item.skill_id.includes("mail")) return "email" as const;
  if (item.skill_id.includes("calendar") || item.skill_id.includes("scheduler")) return "calendar" as const;
  if (item.skill_id.includes("web") || item.skill_id.includes("http")) return "web" as const;
  return "action" as const;
}
