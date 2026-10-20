import { agentApiService } from "../../services/agents/AgentApiService";
import type { ArtifactResponse } from "../../services/artifacts";
import { automationApiService } from "../../services/automations";
import { conversationApiService } from "../../services/conversations";
import { skillApiService } from "../../services/skills";

export interface ArtifactSourceNames {
  agents: Record<string, string>;
  automations: Record<string, string>;
  conversations: Record<string, string>;
  skills: Record<string, string>;
}

export const EMPTY_ARTIFACT_SOURCE_NAMES: ArtifactSourceNames = {
  agents: {}, automations: {}, conversations: {}, skills: {},
};

export async function resolveArtifactSourceNames(
  artifacts: readonly ArtifactResponse[],
  signal?: AbortSignal,
): Promise<ArtifactSourceNames> {
  const names: ArtifactSourceNames = { agents: {}, automations: {}, conversations: {}, skills: {} };
  const agents = new Set<string>();
  const automations = new Set<string>();
  const conversations = new Set<string>();
  const skills = new Set<string>();
  for (const { source } of artifacts) {
    if (source.agent_id) agents.add(source.agent_id);
    if (source.automation_id) automations.add(source.automation_id);
    if (source.conversation_id) conversations.add(source.conversation_id);
    if (source.skill_id) skills.add(source.skill_id);
  }
  if (signal?.aborted) return names;

  // Each source kind fails independently; names are optional enrichment, not listing errors.
  await Promise.allSettled([
    (async () => {
      if (!agents.size) return;
      for (const agent of await agentApiService.listAgents()) {
        if (agents.has(agent.agent_id) && agent.agent_name.trim()) names.agents[agent.agent_id] = agent.agent_name;
      }
    })(),
    (async () => {
      if (!automations.size) return;
      for (const automation of await automationApiService.listAutomations()) {
        if (automations.has(automation.automation_id) && automation.title.trim()) names.automations[automation.automation_id] = automation.title;
      }
    })(),
    (async () => {
      if (!skills.size) return;
      for (const skill of await skillApiService.listSkills()) {
        if (skills.has(skill.skill_id) && skill.name.trim()) names.skills[skill.skill_id] = skill.name;
      }
    })(),
    (async () => {
      if (!conversations.size) return;
      let cursor: string | undefined;
      const seenCursors = new Set<string>();
      // Bound account-wide history scans: old/deleted sources can keep their ID fallback.
      for (let page = 0; page < 5 && conversations.size && !signal?.aborted; page++) {
        const response = await conversationApiService.listConversations(100, cursor);
        for (const conversation of response.items) {
          if (!conversations.has(conversation.conversation_id)) continue;
          if (conversation.title.trim()) names.conversations[conversation.conversation_id] = conversation.title;
          conversations.delete(conversation.conversation_id);
        }
        if (!response.has_more || !response.next_cursor || seenCursors.has(response.next_cursor)) break;
        cursor = response.next_cursor;
        seenCursors.add(cursor);
      }
    })(),
  ]);
  return names;
}
