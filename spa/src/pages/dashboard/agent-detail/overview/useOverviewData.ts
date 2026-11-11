/**
 * Everything the overview shows about an agent beyond the agent record itself.
 *
 * Each part loads on its own, so one failing request leaves its own card saying so instead of an empty list
 * that reads as "none" (the old page swallowed every error into empty lists).
 */

import { useCallback, useEffect, useState } from "react";

import { agentApiService, type Agent2AgentSharingResponse } from "../../../../services/agents/AgentApiService";
import { connectorApiService } from "../../../../services/connectors";
import { knowledgeApiService } from "../../../../services/knowledge";
import { memoryApiService, type MemoryBlockResponse } from "../../../../services/memory";
import { skillApiService } from "../../../../services/skills";
import type { AgentMCPConnection } from "../../../../types/connectors";
import type { FormSchema } from "../../../../types/form";
import type { KnowledgeBase } from "../../../../types/knowledge";
import type { InstalledSkill } from "../../../../types/skills";

export type Loaded<T> = { state: "loading" } | { state: "failed" } | { state: "ready"; value: T };

export interface A2ASharing {
  sharing: Loaded<Agent2AgentSharingResponse>;
  updating: boolean;
  error: string | null;
  setEnabled: (enabled: boolean) => Promise<boolean | null>;
}

export interface OverviewData {
  updateSchema: Loaded<FormSchema>;
  skills: Loaded<InstalledSkill[]>;
  knowledgeBases: Loaded<KnowledgeBase[]>;
  mcpConnections: Loaded<AgentMCPConnection[]>;
  memoryBlocks: Loaded<MemoryBlockResponse[]>;
  a2a: A2ASharing;
}

export function useOverviewData(agentId: string): OverviewData {
  const [updateSchema] = useAgentResource(agentId, loadUpdateSchema);
  const [skills] = useAgentResource(agentId, loadSkills);
  const [knowledgeBases] = useAgentResource(agentId, loadKnowledgeBases);
  const [mcpConnections] = useAgentResource(agentId, loadMcpConnections);
  const [memoryBlocks] = useAgentResource(agentId, loadMemoryBlocks);
  const a2a = useA2ASharing(agentId);
  return { updateSchema, skills, knowledgeBases, mcpConnections, memoryBlocks, a2a };
}

const loadUpdateSchema = (agentId: string) => agentApiService.getUpdateSchema(agentId);
const loadSkills = (agentId: string) => skillApiService.listInstalledSkills(agentId);
const loadKnowledgeBases = (agentId: string) => knowledgeApiService.listAgentKnowledgeBases(agentId);
const loadMcpConnections = (agentId: string) => connectorApiService.listAgentMCPConnections(agentId);
const loadMemoryBlocks = (agentId: string) => memoryApiService.listMemoryBlocks(agentId);
const loadA2ASharing = (agentId: string) => agentApiService.getAgent2AgentSharing(agentId);

/** One agent-scoped fetch, keyed by agent so switching agents never shows the previous agent's data. */
function useAgentResource<T>(agentId: string, load: (agentId: string) => Promise<T>) {
  const [result, setResult] = useState<{ agentId: string; loaded: Loaded<T> } | null>(null);

  useEffect(() => {
    let current = true;
    load(agentId)
      .then((value) => current && setResult({ agentId, loaded: { state: "ready", value } }))
      .catch((error: unknown) => {
        console.error("Error loading agent overview data:", error);
        if (current) setResult({ agentId, loaded: { state: "failed" } });
      });
    return () => {
      current = false;
    };
  }, [agentId, load]);

  const loaded: Loaded<T> = result?.agentId === agentId ? result.loaded : { state: "loading" };
  const replace = useCallback((value: T) => setResult({ agentId, loaded: { state: "ready", value } }), [agentId]);
  return [loaded, replace] as const;
}

function useA2ASharing(agentId: string): A2ASharing {
  const [sharing, replaceSharing] = useAgentResource(agentId, loadA2ASharing);
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** The new enabled state, or null if the change was refused. */
  const setEnabled = useCallback(
    async (enabled: boolean) => {
      setUpdating(true);
      setError(null);
      try {
        const updated = await agentApiService.updateAgent2AgentSharing(agentId, enabled);
        replaceSharing(updated);
        return updated.enabled;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to update Agent2Agent settings.");
        return null;
      } finally {
        setUpdating(false);
      }
    },
    [agentId, replaceSharing]
  );

  return { sharing, updating, error, setEnabled };
}
