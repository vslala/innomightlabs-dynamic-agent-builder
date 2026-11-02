import type { PolicyRef, PolicySummary, Reach, ServiceAccess } from "../../../services/iam";

/** Where an effective policy comes from, as the person reading the page would say it. */
export function sourceLabel(source: string, groupNames: ReadonlyMap<string, string>): string {
  if (source === "implicit") return "Applies to every member";
  if (source === "account owner") return "Account owner";
  if (source === "direct") return "Attached directly";
  if (source.startsWith("group:")) {
    const name = groupNames.get(source.slice("group:".length));
    return name ? `From the group ${name}` : "From a group";
  }
  return source;
}

/** The policies that can still be attached: not already attached, and never the implicit `OwnerAccess`. */
export function attachable(policies: readonly PolicySummary[], attached: readonly PolicyRef[]): PolicySummary[] {
  const held = new Set(attached.map((ref) => ref.policy));
  return policies.filter((summary) => summary.policy !== "OwnerAccess" && !held.has(summary.policy));
}

export const SERVICE_LEVEL_LABEL: Record<ServiceAccess["level"], string> = {
  full: "Full access",
  limited: "Limited",
  none: "No access",
};

/** One line of a service's access: what kind of reach, and the verbs it covers. */
export interface AccessLine {
  kind: "allowed" | "some" | "own" | "denied";
  label: string;
  verbs: string[];
}

/**
 * A service's actions as lines a person reads, the way the AWS console summarises a policy: what's allowed
 * everywhere, on named resources, only on what they own, then what an explicit Deny refuses.
 */
export function accessLines(service: ServiceAccess): AccessLine[] {
  const lines = new Map<string, AccessLine>();
  const add = (kind: AccessLine["kind"], label: string, verb: string) => {
    const key = `${kind}:${label}`;
    const line = lines.get(key) ?? { kind, label, verbs: [] };
    line.verbs.push(verb);
    lines.set(key, line);
  };
  for (const action of service.actions) {
    if (action.level === "denied") add("denied", "Denied", action.verb);
    else if (action.level === "all") add("allowed", "Allowed", action.verb);
    else if (action.level === "some") add("some", `Only on ${action.allow.resources.join(", ")}`, action.verb);
    else if (action.level === "own") add("own", "On what they own", action.verb);
    if (action.level !== "denied" && action.deny.scope) add("denied", deniedLabel(action.deny), action.verb);
  }
  const order: AccessLine["kind"][] = ["allowed", "some", "own", "denied"];
  return [...lines.values()].sort((a, b) => order.indexOf(a.kind) - order.indexOf(b.kind));
}

function deniedLabel(deny: Reach): string {
  return deny.scope === "own" ? "Denied on what they own" : `Denied on ${deny.resources.join(", ")}`;
}
