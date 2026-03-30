import { useOutletContext } from "react-router-dom";

import type { AgentResponse } from "../../../services/agents/AgentApiService";

export interface AgentDetailOutletContext {
  agent: AgentResponse;
}

export function useAgentDetailContext(): AgentDetailOutletContext {
  return useOutletContext<AgentDetailOutletContext>();
}
