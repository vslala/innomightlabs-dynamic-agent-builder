import { Link } from "react-router-dom";
import { Loader2, MessageSquare, Plus, Search, Trash2 } from "lucide-react";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import type { AgentResponse } from "../../../services/agents/AgentApiService";
import type { ConversationResponse } from "../../../types/conversation";

interface ConversationSidebarProps {
  conversations: ConversationResponse[];
  agents: AgentResponse[];
  search: string;
  deletingId: string | null;
  onSearchChange: (value: string) => void;
  onNewConversation: () => void;
  onDeleteConversation: (conversation: ConversationResponse) => void;
}

export function ConversationSidebar({
  conversations,
  agents,
  search,
  deletingId,
  onSearchChange,
  onNewConversation,
  onDeleteConversation,
}: ConversationSidebarProps) {
  return (
    <aside
      className="flex h-full min-h-0 flex-col border-r border-[var(--border-subtle)] bg-white/[0.018]"
      style={{ boxSizing: "border-box", padding: "1.5rem" }}
    >
      <div className="pb-6">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold leading-5 text-[var(--text-primary)]">Conversations</h2>
            <p className="mt-0.5 text-xs text-[var(--text-muted)]">{conversations.length} saved</p>
          </div>
          <Button
            type="button"
            size="icon"
            variant="ghost"
            title="New conversation"
            onClick={onNewConversation}
          >
            <Plus className="h-4 w-4" />
          </Button>
        </div>

        <div className="relative mt-5">
          <Search className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]" />
          <Input
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Search conversations"
            style={{ paddingLeft: "2.75rem" }}
          />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto pb-4">
        <div className="flex min-w-0 flex-col gap-2.5">
          {conversations.length === 0 ? (
            <div className="rounded-xl px-5 py-5 text-sm text-[var(--text-muted)]">No conversations found.</div>
          ) : (
            conversations.map((conversation) => (
              <Link
                key={conversation.conversation_id}
                to={`/dashboard/conversations/${conversation.conversation_id}`}
                className="group flex min-w-0 items-start gap-4 rounded-xl px-5 py-4 text-left transition-colors hover:bg-white/5"
                style={{ boxSizing: "border-box" }}
              >
                <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/5 text-[var(--text-secondary)]">
                  <MessageSquare className="h-4 w-4" />
                </span>
                <span className="min-w-0 flex-1 pr-2">
                  <span className="block truncate text-sm font-medium leading-5 text-[var(--text-primary)]">
                    {conversation.title}
                  </span>
                  <span className="block truncate text-xs leading-5 text-[var(--text-muted)]">
                    {getAgentName(agents, conversation.agent_id)}
                  </span>
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="rounded-md text-red-300 opacity-0 transition-opacity hover:bg-red-500/10 hover:text-red-200 group-hover:opacity-100"
                  style={{ height: "1.75rem", width: "1.75rem" }}
                  disabled={deletingId === conversation.conversation_id}
                  onClick={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    onDeleteConversation(conversation);
                  }}
                  title="Delete conversation"
                >
                  {deletingId === conversation.conversation_id ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Trash2 className="h-4 w-4" />
                  )}
                </Button>
              </Link>
            ))
          )}
        </div>
      </div>
    </aside>
  );
}

function getAgentName(agents: AgentResponse[], agentId: string): string {
  return agents.find((agent) => agent.agent_id === agentId)?.agent_name || "Unknown Agent";
}
