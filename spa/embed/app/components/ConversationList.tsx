import { MessageSquare } from "lucide-react";

import type { WidgetConversation } from "../api";

interface ConversationListProps {
  conversations: WidgetConversation[];
  currentId: string | null;
  onSelect: (conversationId: string) => void;
}

const dateFormat = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });

export function ConversationList({ conversations, currentId, onSelect }: ConversationListProps) {
  if (conversations.length === 0) {
    return <p className="ie-empty">No previous conversations yet.</p>;
  }

  return (
    <ul className="ie-history">
      {conversations.map((conversation) => (
        <li key={conversation.conversation_id}>
          <button
            type="button"
            className="ie-history-item"
            aria-current={conversation.conversation_id === currentId ? "true" : undefined}
            onClick={() => onSelect(conversation.conversation_id)}
          >
            <MessageSquare aria-hidden="true" />
            <span className="ie-history-title">{conversation.title}</span>
            <span className="ie-history-date">
              {dateFormat.format(new Date(conversation.updated_at ?? conversation.created_at))}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
