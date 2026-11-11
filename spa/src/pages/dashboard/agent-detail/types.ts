import { useOutletContext } from "react-router-dom";

import type { AgentResponse } from "../../../services/agents/AgentApiService";

export interface AgentDetailOutletContext {
  agent: AgentResponse;
  /** Replace the agent everywhere in the detail view (the header too) after an edit. */
  onAgentUpdated: (agent: AgentResponse) => void;
}

export function useAgentDetailContext(): AgentDetailOutletContext {
  return useOutletContext<AgentDetailOutletContext>();
}
