import { Bot, CheckCircle2, Loader2, User, Wrench, XCircle } from "lucide-react";
import { buildChatStreamRenderPlan } from '../../../packages/chat-stream-renderer/src';
import { AttachmentChip } from "./AttachmentChip";
import { MarkdownRenderer } from '../ui/markdown-renderer';
import type { AttachmentInfo, Message, ToolActivity } from "../../types/message";

interface ChatStreamRendererProps {
  messages: Message[];
  streamingContent?: string;
  toolActivities?: ToolActivity[];
  statusMessage?: string | null;
  userPicture?: string;
  userName?: string;
  extraNode?: React.ReactNode;
}

function renderAttachments(role: Message["role"], attachments?: AttachmentInfo[]) {
  if (!attachments?.length) {
    return null;
  }

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "0.25rem",
        marginTop: "0.5rem",
        paddingTop: "0.5rem",
        borderTop: role === "user"
          ? "1px solid rgba(255,255,255,0.2)"
          : "1px solid var(--border-subtle)",
      }}
    >
      {attachments.map((attachment, index) => (
        <AttachmentChip
          key={`${attachment.filename}-${index}`}
          filename={attachment.filename}
          size={attachment.size}
          readonly
        />
      ))}
    </div>
  );
}

export function ChatStreamRenderer({
  messages,
  streamingContent,
  toolActivities = [],
  statusMessage,
  userPicture,
  userName,
  extraNode: customExtraNode,
}: ChatStreamRendererProps) {
  const renderAvatar = (role: Message["role"]) => {
    if (role === "user" && userPicture) {
      return (
        <img
          src={userPicture}
          alt={userName || "User"}
          style={{
            width: "2rem",
            height: "2rem",
            borderRadius: "50%",
            flexShrink: 0,
            objectFit: "cover",
          }}
        />
      );
    }

    return (
      <div
        style={{
          width: "2rem",
          height: "2rem",
          borderRadius: "50%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
          backgroundColor: role === "user"
            ? "var(--gradient-start)"
            : "rgba(102, 126, 234, 0.1)",
        }}
      >
        {role === "user" ? (
          <User style={{ height: "1rem", width: "1rem", color: "white" }} />
        ) : (
          <Bot style={{ height: "1rem", width: "1rem", color: "var(--gradient-start)" }} />
        )}
      </div>
    );
  };

  const extraNode = (
    <>
      {toolActivities.length > 0 && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "0.5rem",
            padding: "0.75rem",
            margin: "0.5rem 0",
            borderRadius: "0.5rem",
            backgroundColor: "var(--bg-tertiary)",
            border: "1px solid var(--border-subtle)",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              paddingBottom: "0.5rem",
              borderBottom: "1px solid var(--border-subtle)",
              fontSize: "0.75rem",
              fontWeight: 600,
              color: "var(--text-muted)",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
            }}
          >
            <Wrench style={{ height: "0.875rem", width: "0.875rem" }} />
            Agent Activity
          </div>
          {toolActivities.map((activity) => (
            <div
              key={activity.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                fontSize: "0.875rem",
                color: "var(--text-secondary)",
              }}
            >
              {activity.status === "running" ? (
                <Loader2
                  style={{
                    height: "0.875rem",
                    width: "0.875rem",
                    color: "var(--gradient-start)",
                    animation: "spin 1s linear infinite",
                    flexShrink: 0,
                  }}
                />
              ) : activity.status === "success" ? (
                <CheckCircle2 style={{ height: "0.875rem", width: "0.875rem", color: "#22c55e", flexShrink: 0 }} />
              ) : (
                <XCircle style={{ height: "0.875rem", width: "0.875rem", color: "#ef4444", flexShrink: 0 }} />
              )}
              <span
                style={{
                  fontFamily: "monospace",
                  fontSize: "0.75rem",
                  color: "var(--text-muted)",
                  flexShrink: 0,
                }}
              >
                {activity.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
              </span>
              <span
                style={{
                  fontWeight: 500,
                  color: activity.status === "running" ? "var(--gradient-start)" : "var(--text-primary)",
                }}
              >
                {activity.tool_name.replace(/_/g, " ")}
              </span>
              <span
                style={{
                  color: "var(--text-muted)",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {activity.content}
              </span>
            </div>
          ))}
        </div>
      )}

      {statusMessage && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "0.5rem",
            padding: "0.5rem",
            color: "var(--text-muted)",
            fontSize: "0.875rem",
          }}
        >
          <Loader2 style={{ height: "1rem", width: "1rem", animation: "spin 1s linear infinite" }} />
          {statusMessage}
        </div>
      )}

      {customExtraNode}
    </>
  );

  const plan = buildChatStreamRenderPlan({
    messages,
    getMessageKey: (message) => message.message_id,
    streamingContent,
    hasExtraNode: toolActivities.length > 0 || Boolean(statusMessage) || Boolean(customExtraNode),
  });

  return (
    <>
      {plan.map((item) => {
        if (item.kind === "message") {
          const msg = item.message;
          return (
            <div
              key={item.key}
              style={{
                display: "flex",
                gap: "0.75rem",
                alignItems: "flex-start",
                flexDirection: msg.role === "user" ? "row-reverse" : "row",
              }}
            >
              {renderAvatar(msg.role)}
              <div
                style={{
                  maxWidth: "70%",
                  padding: "0.75rem 1rem",
                  borderRadius: "1rem",
                  backgroundColor: msg.role === "user"
                    ? "var(--gradient-start)"
                    : "var(--bg-secondary)",
                  color: msg.role === "user" ? "white" : "var(--text-primary)",
                  wordBreak: "break-word",
                  lineHeight: "1.5",
                  ...(msg.role === "user" ? { whiteSpace: "pre-wrap" as const } : {}),
                }}
              >
                {msg.role === "assistant" ? <MarkdownRenderer content={msg.content} /> : msg.content}
                {renderAttachments(msg.role, msg.attachments)}
              </div>
            </div>
          );
        }

        if (item.kind === "streaming") {
          return (
            <div key={item.key} style={{ display: "flex", gap: "0.75rem", alignItems: "flex-start" }}>
              {renderAvatar("assistant")}
              <div
                style={{
                  maxWidth: "70%",
                  padding: "0.75rem 1rem",
                  borderRadius: "1rem",
                  backgroundColor: "var(--bg-secondary)",
                  color: "var(--text-primary)",
                  wordBreak: "break-word",
                  lineHeight: "1.5",
                }}
              >
                <MarkdownRenderer content={item.content} />
                <span
                  style={{
                    display: "inline-block",
                    width: "0.5rem",
                    height: "1rem",
                    marginLeft: "0.125rem",
                    backgroundColor: "var(--gradient-start)",
                    animation: "blink 1s infinite",
                  }}
                />
              </div>
            </div>
          );
        }

        if (item.kind === "extra") {
          return <div key={item.key}>{extraNode}</div>;
        }

        return null;
      })}
    </>
  );
}
