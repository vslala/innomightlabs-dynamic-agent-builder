import { useLayoutEffect, useRef, useState } from "react";
import { buildChatStreamRenderPlan } from "../../../packages/chat-stream-renderer/src";
import { ArrowDown, Sparkles, Wrench } from "lucide-react";

import { parseFormSubmission } from "../../../src/components/chat/submittedFormParser";
import type { ChatMessage, PendingForm } from "../useChat";
import { FormCard } from "./FormCard";
import { Markdown } from "./Markdown";

interface MessageListProps {
  agentName: string;
  greeting: string;
  messages: ChatMessage[];
  streaming: string;
  activeTool: string | null;
  pendingForm: PendingForm | null;
  isSending: boolean;
  isLoading: boolean;
  /** A question the visitor can send with one click (a default prompt that isn't sent automatically). */
  suggestion?: { label: string; onSelect: () => void } | null;
  onSubmitForm: (content: string, display: string) => void;
}

/** How close to the bottom (px) still counts as "following" the conversation. */
const FOLLOW_THRESHOLD = 48;

export function MessageList({
  agentName,
  greeting,
  messages,
  streaming,
  activeTool,
  pendingForm,
  isSending,
  isLoading,
  suggestion,
  onSubmitForm,
}: MessageListProps) {
  const listRef = useRef<HTMLDivElement>(null);
  // Follow new text only while the visitor is at the bottom; scrolling up stops it. Only the list
  // itself is scrolled (never scrollIntoView), so the host page around the iframe never moves.
  const followingRef = useRef(true);
  const [showJump, setShowJump] = useState(false);
  const lastMessage = messages[messages.length - 1];

  const scrollToBottom = () => {
    const list = listRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  };

  const onScroll = () => {
    const list = listRef.current;
    if (!list) return;
    followingRef.current = list.scrollHeight - list.scrollTop - list.clientHeight < FOLLOW_THRESHOLD;
    setShowJump(!followingRef.current);
  };

  // The visitor's own new message always brings the view back to the bottom.
  useLayoutEffect(() => {
    if (lastMessage?.role === "user") followingRef.current = true;
  }, [lastMessage]);

  useLayoutEffect(() => {
    if (followingRef.current) scrollToBottom();
  }, [messages, streaming, activeTool, pendingForm, isLoading]);

  if (isLoading) {
    return (
      <div className="ie-messages ie-messages-loading" aria-busy="true">
        <span className="ie-spinner" />
      </div>
    );
  }

  const plan = buildChatStreamRenderPlan({
    messages,
    getMessageKey: (message) => message.id,
    streamingContent: streaming,
    hasExtraNode: Boolean(pendingForm),
    isLoading: isSending,
  });

  return (
    <div className="ie-messages-wrap">
      <div
        ref={listRef}
        className="ie-messages"
        role="log"
        aria-live="polite"
        aria-label={`Conversation with ${agentName}`}
        onScroll={onScroll}
      >
        <div className="ie-bubble ie-bubble-assistant ie-greeting">
          <Markdown content={greeting} />
        </div>

        {suggestion && (
          <button type="button" className="ie-suggestion" onClick={suggestion.onSelect}>
            <Sparkles aria-hidden="true" />
            <span className="ie-suggestion-text">{suggestion.label}</span>
          </button>
        )}

        {plan.map((item) => {
          if (item.kind === "message") return <MessageBubble key={item.key} message={item.message} />;
          if (item.kind === "streaming") {
            return (
              <div key={item.key} className="ie-bubble ie-bubble-assistant">
                <Markdown content={item.content} />
              </div>
            );
          }
          if (item.kind === "extra" && pendingForm) {
            return <FormCard key={item.key} pending={pendingForm} disabled={isSending} onSubmit={onSubmitForm} />;
          }
          return activeTool ? (
            <div key={item.key} className="ie-tool">
              <Wrench aria-hidden="true" />
              Using {activeTool}…
            </div>
          ) : (
            <div key={item.key} className="ie-typing" aria-label={`${agentName} is typing`}>
              <span />
              <span />
              <span />
            </div>
          );
        })}
      </div>
      {showJump && (
        <button
          type="button"
          className="ie-jump"
          aria-label="Jump to latest message"
          onClick={() => {
            followingRef.current = true;
            setShowJump(false);
            scrollToBottom();
          }}
        >
          <ArrowDown aria-hidden="true" />
        </button>
      )}
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    const submission = message.display ? null : parseFormSubmission(message.content);
    return (
      <div className="ie-bubble ie-bubble-user">
        {message.display ?? (submission ? `Submitted: ${submission.label}` : message.content)}
      </div>
    );
  }

  return (
    <div className={message.isError ? "ie-bubble ie-bubble-assistant ie-bubble-error" : "ie-bubble ie-bubble-assistant"}>
      <Markdown content={message.content} />
    </div>
  );
}
