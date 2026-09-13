/**
 * Collapsed-card summaries: what a step does, in one line, without expanding it.
 */

import type {
  AutomationActionCatalogItem,
  AutomationNode,
  AutomationTrigger,
  SkillActionConfig,
} from "../../../../types/automation";

export type StepIconKind = "agent" | "email" | "calendar" | "web" | "condition" | "action";

export interface StepSummary {
  /** WHEN / THEN / IF label shown in the card gutter. */
  kind: "when" | "then" | "if" | "end";
  icon: StepIconKind;
  title: string;
  subtitle: string | null;
}

export function skillActionOf(node: AutomationNode): SkillActionConfig | null {
  const config = node.config as Record<string, unknown>;
  if (config.action_type === "skill_action") {
    const action = typeof config.action === "string" ? config.action : "";
    if (!action) return null;
    return {
      action_type: "skill_action",
      installed_skill_id:
        typeof config.installed_skill_id === "string" ? config.installed_skill_id : null,
      skill_id: typeof config.skill_id === "string" ? config.skill_id : null,
      action,
      arguments:
        config.arguments && typeof config.arguments === "object"
          ? (config.arguments as Record<string, unknown>)
          : {},
    };
  }
  if (config.action_type === "invoke_agent") {
    return {
      action_type: "skill_action",
      installed_skill_id: null,
      skill_id: "agent_invocation",
      action: "invoke",
      arguments: {
        agent_id: config.agent_id,
        prompt_template: config.prompt_template,
      },
    };
  }
  return null;
}

export function catalogItemKey(item: AutomationActionCatalogItem): string {
  return `${item.installed_skill_id || item.skill_id}::${item.action}`;
}

export function findCatalogItem(
  node: AutomationNode,
  catalog: AutomationActionCatalogItem[]
): AutomationActionCatalogItem | null {
  const config = skillActionOf(node);
  if (!config) return null;
  const byInstalled = config.installed_skill_id
    ? catalog.find(
        (item) =>
          item.installed_skill_id === config.installed_skill_id && item.action === config.action
      )
    : null;
  return (
    byInstalled ??
    catalog.find((item) => item.skill_id === config.skill_id && item.action === config.action) ??
    null
  );
}

export function iconKindFor(node: AutomationNode, item: AutomationActionCatalogItem | null): StepIconKind {
  if (node.type === "condition") return "condition";
  const skillId = item?.skill_id ?? skillActionOf(node)?.skill_id ?? "";
  if (skillId === "agent_invocation") return "agent";
  if (skillId.includes("mail")) return "email";
  if (skillId.includes("calendar") || skillId.includes("scheduler")) return "calendar";
  if (skillId.includes("web") || skillId.includes("http")) return "web";
  return "action";
}

export function describeStep(
  node: AutomationNode,
  catalog: AutomationActionCatalogItem[]
): StepSummary {
  if (node.type === "condition") {
    return {
      kind: "if",
      icon: "condition",
      title: node.name || "Condition",
      subtitle: describeCondition(node),
    };
  }

  const item = findCatalogItem(node, catalog);
  return {
    kind: "then",
    icon: iconKindFor(node, item),
    title: node.name || item?.label || "New step",
    subtitle: describeAction(node, item),
  };
}

function describeAction(
  node: AutomationNode,
  item: AutomationActionCatalogItem | null
): string | null {
  const config = skillActionOf(node);
  if (!config) return "No action chosen yet";
  const primary = primaryArgument(config, item);
  const label = item?.label ?? `${config.skill_id ?? "Skill"}: ${config.action}`;
  return primary ? `${label} · ${primary}` : label;
}

/**
 * First filled-in argument, preferring the action form's own field order so the
 * summary shows whatever the skill considers most important.
 */
function primaryArgument(
  config: SkillActionConfig,
  item: AutomationActionCatalogItem | null
): string | null {
  const order = item?.action_form?.form_inputs.map((input) => input.name) ?? Object.keys(config.arguments);
  for (const name of order) {
    const value = config.arguments[name];
    if (value === undefined || value === null || value === "") continue;
    const text = typeof value === "string" ? value : JSON.stringify(value);
    const collapsed = text.replace(/\s+/g, " ").trim();
    if (!collapsed) continue;
    return collapsed.length > 64 ? `${collapsed.slice(0, 64)}…` : collapsed;
  }
  return null;
}

export function describeCondition(node: AutomationNode): string | null {
  const expression = typeof node.config.expression === "string" ? node.config.expression : "";
  return expression.trim() ? expression.trim() : "No condition set";
}

export function describeTrigger(trigger: AutomationTrigger): string {
  if (trigger.type === "schedule") {
    const cron = typeof trigger.config.cron_expression === "string" ? trigger.config.cron_expression : "";
    const timezone = typeof trigger.config.timezone === "string" ? trigger.config.timezone : "UTC";
    return cron ? `${describeCron(cron)} · ${timezone}` : "Schedule not set";
  }
  if (trigger.type === "webhook") return "Incoming webhook";
  return "Run manually or from a test";
}

const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

/**
 * Plain-language cron for the common shapes the schedule form produces.
 * Anything unusual falls back to the expression itself.
 */
export function describeCron(expression: string): string {
  const parts = expression.trim().split(/\s+/);
  if (parts.length !== 5) return expression;
  const [minute, hour, dayOfMonth, month, weekday] = parts;
  if (!/^\d+$/.test(minute) || !/^\d+$/.test(hour)) return expression;
  const time = `${hour.padStart(2, "0")}:${minute.padStart(2, "0")}`;

  if (dayOfMonth === "*" && month === "*") {
    if (weekday === "*") return `Every day at ${time}`;
    if (weekday === "1-5") return `Every weekday at ${time}`;
    if (/^\d$/.test(weekday)) return `Every ${WEEKDAYS[Number(weekday) % 7]} at ${time}`;
  }
  if (month === "*" && weekday === "*" && /^\d+$/.test(dayOfMonth)) {
    return `Day ${dayOfMonth} of every month at ${time}`;
  }
  return expression;
}
