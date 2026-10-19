import { Library, Plug, Zap, type LucideIcon } from "lucide-react";
import type { AgentAccess, AgentAttachedCounts, AgentResponse } from "../../services/agents/AgentApiService";

/** The agent list's tabs are how the caller reaches each agent, so every agent is in exactly one. */
export const AGENT_TABS: { access: AgentAccess; label: string }[] = [
  { access: "owner", label: "Mine" },
  { access: "shared", label: "Shared with me" },
  { access: "admin", label: "Admin view" },
];

export type AgentSort = "recent" | "used" | "newest" | "name";

export const AGENT_SORTS: { value: AgentSort; label: string }[] = [
  { value: "recent", label: "Recently used" },
  { value: "used", label: "Most used" },
  { value: "newest", label: "Newest" },
  { value: "name", label: "A–Z" },
];

export const ATTACHMENTS: { key: keyof AgentAttachedCounts; label: string; Icon: LucideIcon }[] = [
  { key: "knowledge_bases", label: "Knowledge base", Icon: Library },
  { key: "connectors", label: "Connectors", Icon: Plug },
  { key: "skills", label: "Skills", Icon: Zap },
];

/** Whether the agent has every one of the required attachments; one whose counts haven't loaded has none. */
export function hasAttachments(counts: AgentAttachedCounts | undefined, required: (keyof AgentAttachedCounts)[]): boolean {
  return required.every((key) => (counts?.[key] ?? 0) > 0);
}

/** What the agent does, in a line: its description, else the start of its persona. */
export function agentSummary(agent: AgentResponse): string {
  return agent.agent_description?.trim() || agent.agent_persona;
}

/** Every word of the query appears in the agent's name, summary or provider. */
export function matchesQuery(agent: AgentResponse, query: string): boolean {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return true;
  const haystack = [agent.agent_name, agentSummary(agent), agent.agent_provider, agent.agent_model ?? ""]
    .join(" ")
    .toLowerCase();
  return words.every((word) => haystack.includes(word));
}

function lastUsed(agent: AgentResponse): number {
  return agent.last_used_at ? Date.parse(agent.last_used_at) : 0;
}

const COMPARE: Record<AgentSort, (a: AgentResponse, b: AgentResponse) => number> = {
  recent: (a, b) => lastUsed(b) - lastUsed(a),
  used: (a, b) => (b.use_count ?? 0) - (a.use_count ?? 0),
  newest: (a, b) => Date.parse(b.created_at) - Date.parse(a.created_at),
  name: (a, b) => a.agent_name.localeCompare(b.agent_name),
};

/** A sorted copy; ties fall back to A–Z so the order is stable. */
export function sortAgents(agents: AgentResponse[], sort: AgentSort): AgentResponse[] {
  return [...agents].sort((a, b) => COMPARE[sort](a, b) || COMPARE.name(a, b));
}

/** The agents you used most recently, newest first; never-used agents are left out. */
export function recentAgents(agents: AgentResponse[], limit: number): AgentResponse[] {
  return sortAgents(agents, "recent").filter((agent) => agent.last_used_at).slice(0, limit);
}

/** "5m ago", "3h ago", "2d ago". */
export function timeAgo(iso: string, now: number = Date.now()): string {
  const minutes = Math.max(0, Math.round((now - Date.parse(iso)) / 60_000));
  if (minutes < 60) return `${Math.max(minutes, 1)}m ago`;
  const hours = Math.round(minutes / 60);
  return hours < 48 ? `${hours}h ago` : `${Math.round(hours / 24)}d ago`;
}
