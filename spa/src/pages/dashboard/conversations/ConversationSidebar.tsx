import { Link } from "react-router-dom";
import { Loader2, Plus, Search, Trash2 } from "lucide-react";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Pill } from "../../../components/ui/pill";
import { getAgentIcon } from "../../../lib/agentIcons";
import type { AgentResponse } from "../../../services/agents/AgentApiService";
import type { ConversationResponse } from "../../../types/conversation";
import { formatRelativeTime } from "../../../utils/time";
import styles from "./ConversationSidebar.module.css";

const AGENT_AVATAR_PALETTE = [
  { bg: "rgba(87, 157, 255, 0.16)", fg: "#579dff" },
  { bg: "rgba(168, 130, 255, 0.16)", fg: "#a882ff" },
  { bg: "rgba(76, 217, 165, 0.16)", fg: "#4cd9a5" },
  { bg: "rgba(255, 179, 71, 0.16)", fg: "#ffb347" },
  { bg: "rgba(255, 122, 158, 0.16)", fg: "#ff7a9e" },
  { bg: "rgba(94, 219, 219, 0.16)", fg: "#5edbdb" },
];

function getAgentAvatarStyle(agentId: string) {
  let hash = 0;
  for (let i = 0; i < agentId.length; i++) {
    hash = (hash * 31 + agentId.charCodeAt(i)) >>> 0;
  }
  return AGENT_AVATAR_PALETTE[hash % AGENT_AVATAR_PALETTE.length];
}

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
    <aside className={styles.sidebar}>
      <div className={styles.header}>
        <div className={styles.headerTop}>
          <div>
            <h2 className={styles.headerTitle}>Conversations</h2>
            <p className={styles.headerCount}>{conversations.length} saved</p>
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

        <div className={styles.searchWrap}>
          <Search className={styles.searchIcon} />
          <Input
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Search conversations"
            style={{ paddingLeft: "2.75rem" }}
          />
        </div>
      </div>

      <div className={styles.list}>
        <div className={styles.listInner}>
          {conversations.length === 0 ? (
            <div className={styles.emptyState}>No conversations found.</div>
          ) : (
            conversations.map((conversation) => {
              const agentName = getAgentName(agents, conversation.agent_id);
              const avatar = getAgentAvatarStyle(conversation.agent_id);
              const AgentIcon = getAgentIcon(agentName);
              const lastActivity = conversation.updated_at ?? conversation.created_at;
              return (
                <Link
                  key={conversation.conversation_id}
                  to={`/dashboard/conversations/${conversation.conversation_id}`}
                  className={`group ${styles.card}`}
                >
                  <div className={styles.cardTopRow}>
                    <Pill
                      size="sm"
                      className={styles.cardTag}
                      style={{ backgroundColor: avatar.bg, color: avatar.fg }}
                    >
                      <AgentIcon className={styles.cardTagIcon} />
                      <span className={styles.cardTagText}>{agentName}</span>
                    </Pill>
                    <div className={styles.cardMeta}>
                      <span className={styles.cardTime}>
                        {formatRelativeTime(lastActivity)}
                      </span>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className={styles.deleteButton}
                        disabled={deletingId === conversation.conversation_id}
                        onClick={(event) => {
                          event.preventDefault();
                          event.stopPropagation();
                          onDeleteConversation(conversation);
                        }}
                        title="Delete conversation"
                      >
                        {deletingId === conversation.conversation_id ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Trash2 className="h-3.5 w-3.5" />
                        )}
                      </Button>
                    </div>
                  </div>
                  <span className={styles.cardTitle}>
                    {conversation.title}
                  </span>
                  {conversation.description && (
                    <span className={styles.cardDescription}>
                      {conversation.description}
                    </span>
                  )}
                </Link>
              );
            })
          )}
        </div>
      </div>
    </aside>
  );
}

function getAgentName(agents: AgentResponse[], agentId: string): string {
  return agents.find((agent) => agent.agent_id === agentId)?.agent_name || "Unknown Agent";
}
