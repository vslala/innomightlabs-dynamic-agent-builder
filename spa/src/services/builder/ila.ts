/**
 * Ila, the solution builder. She isn't one of the person's agents: her conversations carry this id
 * (ILA_AGENT_ID in api/src/builder/ila.py), and her chat routes live under /builder.
 */
export const ILA_AGENT_ID = "innomightlabs-ila";
export const ILA_NAME = "Ila";

export function isIla(agentId: string | undefined | null): boolean {
  return agentId === ILA_AGENT_ID;
}

/** Where a conversation's chat routes (send-message, turns) live. */
export function chatPath(agentId: string, conversationId: string): string {
  return isIla(agentId) ? `/builder/${conversationId}` : `/agents/${agentId}/${conversationId}`;
}

/** An agent's name for display, including Ila, who isn't in the agents list. */
export function agentDisplayName(agents: { agent_id: string; agent_name: string }[], agentId: string): string {
  if (isIla(agentId)) return ILA_NAME;
  return agents.find((agent) => agent.agent_id === agentId)?.agent_name || "Unknown Agent";
}

/**
 * Whether a conversation shows the tools its turns ran. Never for Ila: her tools (forms, plans) are how
 * she talks to the person, and the person sees their results, not the calls.
 */
export function showsToolActivity(agentId: string | undefined | null, flagEnabled: boolean): boolean {
  return flagEnabled && !isIla(agentId);
}
