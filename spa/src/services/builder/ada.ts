/**
 * Ada, the solution builder. She isn't one of the person's agents: her conversations carry this id
 * (ADA_AGENT_ID in api/src/builder/ada.py), and her chat routes live under /builder.
 */
export const ADA_AGENT_ID = "innomightlabs-ada";
export const ADA_NAME = "Ada";

export function isAda(agentId: string | undefined | null): boolean {
  return agentId === ADA_AGENT_ID;
}

/** Where a conversation's chat routes (send-message, turns) live. */
export function chatPath(agentId: string, conversationId: string): string {
  return isAda(agentId) ? `/builder/${conversationId}` : `/agents/${agentId}/${conversationId}`;
}

/** An agent's name for display, including Ada, who isn't in the agents list. */
export function agentDisplayName(agents: { agent_id: string; agent_name: string }[], agentId: string): string {
  if (isAda(agentId)) return ADA_NAME;
  return agents.find((agent) => agent.agent_id === agentId)?.agent_name || "Unknown Agent";
}

/**
 * Whether a conversation shows the tools its turns ran. Never for Ada: her tools (forms, plans) are how
 * she talks to the person, and the person sees their results, not the calls.
 */
export function showsToolActivity(agentId: string | undefined | null, flagEnabled: boolean): boolean {
  return flagEnabled && !isAda(agentId);
}
