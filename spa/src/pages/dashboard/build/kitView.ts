import type { KitPlan, KitSummary, KitVersion, PlanAction } from "../../../services/kits/KitApiService";

/** How each kind is named to people, one and many. Kinds the SPA doesn't know yet show their own name. */
const KIND_NAMES: Record<string, [string, string]> = {
  Agent: ["agent", "agents"],
  KnowledgeBase: ["knowledge base", "knowledge bases"],
  WidgetKey: ["chat widget", "chat widgets"],
  McpConnection: ["tool connection", "tool connections"],
};

/** The order kinds are listed in: what people chat with first. */
const KIND_ORDER = ["Agent", "KnowledgeBase", "WidgetKey", "McpConnection"];

export function kindName(kind: string, count = 1): string {
  const [one, many] = KIND_NAMES[kind] ?? [kind, kind];
  return count === 1 ? one : many;
}

/** "2 agents · 1 knowledge base · 1 chat widget" */
export function kitContents(counts: Record<string, number>): string {
  const kinds = Object.keys(counts).sort((a, b) => rank(a) - rank(b));
  const parts = kinds.filter((kind) => counts[kind] > 0).map((kind) => `${counts[kind]} ${kindName(kind, counts[kind])}`);
  return parts.length > 0 ? parts.join(" · ") : "Nothing in it";
}

function rank(kind: string): number {
  const index = KIND_ORDER.indexOf(kind);
  return index === -1 ? KIND_ORDER.length : index;
}

/** The kit's state, as its badge shows it. */
export function kitStatus(kit: KitSummary): { status: "active" | "inactive"; label: string } {
  return kit.status === "removed" ? { status: "inactive", label: "Removed" } : { status: "active", label: `v${kit.current_version}` };
}

/** What a version did, in a few words. */
export function versionLabel(version: KitVersion): string {
  if (version.action === "remove") return "Removed everything";
  if (version.action === "rollback") return `Rolled back to v${version.rolled_back_to}`;
  return version.version === 1 ? "Built" : "Changed";
}

/** A version the kit can go back to: not the current one, not a removal, and one that finished. */
export function canRollBackTo(version: KitVersion, kit: KitSummary): boolean {
  return kit.status === "active" && !version.current && version.action !== "remove" && version.status === "applied";
}

export const PLAN_ACTIONS: Record<PlanAction, { status: "success" | "info" | "no_status" | "error"; label: string }> = {
  create: { status: "success", label: "Create" },
  update: { status: "info", label: "Update" },
  unchanged: { status: "no_status", label: "Keep" },
  remove: { status: "error", label: "Delete" },
};

/** The steps worth showing: anything that changes, plus what was edited outside the kit (left as it is). */
export function changingSteps(plan: KitPlan) {
  return plan.steps.filter((step) => step.action !== "unchanged" || step.drift.length > 0);
}
