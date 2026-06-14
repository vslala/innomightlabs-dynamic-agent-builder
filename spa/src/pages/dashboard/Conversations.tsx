import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { conversationApiService } from "../../services/conversations";
import { agentApiService, type AgentResponse } from "../../services/agents/AgentApiService";
import type { ConversationResponse } from "../../types/conversation";
import { userVisibleConversations } from "../../utils/conversations";
import { ConversationSidebar } from "./conversations/ConversationSidebar";
import {
  ConversationStartComposer,
  type ConversationStartMode,
} from "./conversations/ConversationStartComposer";

export function Conversations() {
  const navigate = useNavigate();
  const [conversations, setConversations] = useState<ConversationResponse[]>([]);
  const [agents, setAgents] = useState<AgentResponse[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [prompt, setPrompt] = useState("");
  const [mode, setMode] = useState<ConversationStartMode>("chat");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    try {
      setError(null);
      const [conversationsData, agentsData] = await Promise.all([
        conversationApiService.listConversations(50),
        agentApiService.listAgents(),
      ]);
      setConversations(userVisibleConversations(conversationsData.items));
      setAgents(agentsData);
      setSelectedAgentId((current) => current || agentsData[0]?.agent_id || "");
    } catch (err) {
      setError("Failed to load conversations. Please try again.");
      console.error("Error loading conversations:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const filteredConversations = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return conversations;
    return conversations.filter((conversation) => {
      const agentName = getAgentName(agents, conversation.agent_id).toLowerCase();
      return (
        conversation.title.toLowerCase().includes(query) ||
        (conversation.description || "").toLowerCase().includes(query) ||
        agentName.includes(query)
      );
    });
  }, [agents, conversations, search]);

  const handleStartConversation = async () => {
    const message = prompt.trim();
    if (!message || !selectedAgentId || creating) return;

    setCreating(true);
    setError(null);
    try {
      const conversation = await conversationApiService.createConversation({
        title: titleFromPrompt(message, mode),
        agent_id: selectedAgentId,
      });
      setPrompt("");
      navigate(`/dashboard/conversations/${conversation.conversation_id}`, {
        state: mode === "image" ? { initialImagePrompt: message } : { initialMessage: message },
      });
    } catch (err) {
      setError("Failed to start conversation. Please try again.");
      console.error("Error starting conversation:", err);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (conversation: ConversationResponse) => {
    setDeletingId(conversation.conversation_id);
    try {
      await conversationApiService.deleteConversation(conversation.conversation_id);
      setConversations((items) =>
        items.filter((item) => item.conversation_id !== conversation.conversation_id)
      );
    } catch (err) {
      setError("Failed to delete conversation. Please try again.");
      console.error("Error deleting conversation:", err);
    } finally {
      setDeletingId(null);
    }
  };

  const handleNewConversation = () => {
    setPrompt("");
    setMode("chat");
  };

  if (loading) {
    return (
      <div className="flex h-[32rem] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-[var(--gradient-start)]" />
      </div>
    );
  }

  return (
    <div className="grid h-full min-h-[calc(100vh-4rem)] grid-cols-1 bg-[var(--bg-dark)] lg:grid-cols-[24rem_minmax(0,1fr)]">
      <ConversationSidebar
        conversations={filteredConversations}
        agents={agents}
        search={search}
        deletingId={deletingId}
        onSearchChange={setSearch}
        onNewConversation={handleNewConversation}
        onDeleteConversation={handleDelete}
      />

      <main className="flex min-w-0 items-center justify-center px-8 py-16 lg:px-16 xl:px-24">
        <ConversationStartComposer
          agents={agents}
          selectedAgentId={selectedAgentId}
          prompt={prompt}
          mode={mode}
          creating={creating}
          error={error}
          onAgentChange={(agentId) => {
            setSelectedAgentId(agentId);
            const nextAgent = agents.find((agent) => agent.agent_id === agentId);
            if (!nextAgent?.capabilities?.includes("image_generation")) {
              setMode("chat");
            }
          }}
          onPromptChange={setPrompt}
          onModeChange={setMode}
          onSubmit={handleStartConversation}
          onCreateAgent={() => navigate("/dashboard/agents/new")}
        />
      </main>
    </div>
  );
}

function getAgentName(agents: AgentResponse[], agentId: string): string {
  return agents.find((agent) => agent.agent_id === agentId)?.agent_name || "Unknown Agent";
}

function titleFromPrompt(prompt: string, mode: ConversationStartMode): string {
  const normalized = prompt.replace(/\s+/g, " ").trim();
  const prefix = mode === "image" ? "Image: " : "";
  const maxLength = mode === "image" ? 53 : 60;
  if (normalized.length <= maxLength) return `${prefix}${normalized}` || "New conversation";
  return `${prefix}${normalized.slice(0, maxLength - 3).trim()}...`;
}
