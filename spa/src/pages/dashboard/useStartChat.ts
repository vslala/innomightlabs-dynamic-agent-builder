import { useState } from "react";
import { useNavigate } from "react-router-dom";

import type { AgentResponse } from "../../services/agents/AgentApiService";
import { conversationApiService } from "../../services/conversations";

/** Creates a conversation with an agent and opens it. `onError` receives the agent that couldn't be reached. */
export function useStartChat(onError: (agent: AgentResponse) => void) {
  const navigate = useNavigate();
  const [startingWith, setStartingWith] = useState<string | null>(null);

  const startChat = async (agent: Pick<AgentResponse, "agent_id" | "agent_name">) => {
    setStartingWith(agent.agent_id);
    try {
      const conversation = await conversationApiService.createConversation({
        title: `Chat with ${agent.agent_name}`,
        agent_id: agent.agent_id,
      });
      navigate(`/dashboard/conversations/${conversation.conversation_id}`);
    } catch (err) {
      console.error("Error starting conversation:", err);
      onError(agent as AgentResponse);
      setStartingWith(null);
    }
  };

  return { startChat, startingWith };
}
