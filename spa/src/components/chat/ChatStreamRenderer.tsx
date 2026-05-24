import { useEffect, useState } from "react";
import { CheckCircle2, ExternalLink, Image as ImageIcon, Loader2, User, Wrench, XCircle } from "lucide-react";
import { buildChatStreamRenderPlan } from '../../../packages/chat-stream-renderer/src';
import { AttachmentChip } from "./AttachmentChip";
import { MarkdownRenderer } from '../ui/markdown-renderer';
import { SubmittedFormMessage } from "./SubmittedFormMessage";
import { isSubmittedFormMessage } from "./submittedFormParser";
import type { AttachmentInfo, Message, MessageImage, ToolActivity } from "../../types/message";

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

function ImagePreview({ image }: { image: MessageImage }) {
  const [failed, setFailed] = useState(false);
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const label = image.revised_prompt || image.prompt || image.filename;

  useEffect(() => {
    let active = true;
    let nextObjectUrl: string | null = null;

    async function loadImage() {
      if (!image.url) {
        setFailed(true);
        return;
      }

      setFailed(false);
      setObjectUrl(null);

      try {
        const token = localStorage.getItem("auth_token");
        const response = await fetch(image.url, {
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        });

        if (!response.ok) {
          throw new Error(`Image request failed with ${response.status}`);
        }

        const blob = await response.blob();
        nextObjectUrl = URL.createObjectURL(blob);
        if (active) {
          setObjectUrl(nextObjectUrl);
        } else {
          URL.revokeObjectURL(nextObjectUrl);
        }
      } catch {
        if (active) {
          setFailed(true);
        }
      }
    }

    loadImage();

    return () => {
      active = false;
      if (nextObjectUrl) {
        URL.revokeObjectURL(nextObjectUrl);
      }
    };
  }, [image.url]);

  if (!image.url || failed) {
    return (
      <div
        style={{
          minHeight: "16rem",
          borderRadius: "0.75rem",
          border: "1px solid var(--border-subtle)",
          backgroundColor: "var(--bg-tertiary)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: "0.75rem",
          padding: "1.5rem",
          color: "var(--text-muted)",
          textAlign: "center",
        }}
      >
        <ImageIcon style={{ height: "2rem", width: "2rem", color: "var(--text-muted)" }} />
        <div style={{ maxWidth: "28rem" }}>
          <div style={{ color: "var(--text-primary)", fontWeight: 600, marginBottom: "0.25rem" }}>
            Image preview unavailable
          </div>
          <div style={{ fontSize: "0.875rem", lineHeight: 1.5 }}>
            The image file could not be loaded. It may still be processing or unavailable in storage.
          </div>
        </div>
      </div>
    );
  }

  if (!objectUrl) {
    return (
      <div
        style={{
          minHeight: "16rem",
          borderRadius: "0.75rem",
          border: "1px solid var(--border-subtle)",
          backgroundColor: "var(--bg-tertiary)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--text-muted)",
        }}
      >
        <Loader2 style={{ height: "1.5rem", width: "1.5rem", animation: "spin 1s linear infinite" }} />
      </div>
    );
  }

  return (
    <a
      href={objectUrl}
      target="_blank"
      rel="noreferrer"
      title={label}
      style={{
        display: "block",
        borderRadius: "0.75rem",
        overflow: "hidden",
        border: "1px solid var(--border-subtle)",
        backgroundColor: "var(--bg-tertiary)",
        position: "relative",
      }}
    >
      <img
        src={objectUrl}
        alt={label}
        onError={() => setFailed(true)}
        style={{
          display: "block",
          width: "100%",
          maxHeight: "34rem",
          objectFit: "contain",
          backgroundColor: "#101018",
        }}
      />
      <span
        style={{
          position: "absolute",
          right: "0.75rem",
          top: "0.75rem",
          width: "2rem",
          height: "2rem",
          borderRadius: "999px",
          backgroundColor: "rgba(0, 0, 0, 0.55)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <ExternalLink style={{ height: "1rem", width: "1rem", color: "white" }} />
      </span>
    </a>
  );
}

function renderImages(images?: MessageImage[]) {
  if (!images?.length) {
    return null;
  }

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 18rem), 1fr))",
        gap: "0.75rem",
        marginTop: "0.875rem",
      }}
    >
      {images.map((image) => <ImagePreview key={image.image_id} image={image} />)}
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
    if (role === "assistant") {
      return null;
    }

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
            opacity: 0.9,
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
          backgroundColor: "rgba(255, 255, 255, 0.12)",
        }}
      >
        <User style={{ height: "1rem", width: "1rem", color: "rgba(255, 255, 255, 0.86)" }} />
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
            borderRadius: "0.75rem",
            backgroundColor: "rgba(255, 255, 255, 0.045)",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              paddingBottom: "0.5rem",
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
          const isFormSubmission = msg.role === "user" && isSubmittedFormMessage(msg);
          return (
            <div
              key={item.key}
              style={{
                display: "flex",
                gap: msg.role === "user" ? "0.75rem" : 0,
                alignItems: "flex-start",
                flexDirection: msg.role === "user" ? "row-reverse" : "row",
                width: "100%",
              }}
            >
              {renderAvatar(msg.role)}
              <div
                style={{
                  width: msg.role === "assistant" || msg.images?.length ? "100%" : "fit-content",
                  maxWidth: msg.role === "assistant" || msg.images?.length ? "100%" : "min(72%, 42rem)",
                  padding: msg.role === "assistant"
                    ? msg.images?.length ? "0.5rem 0" : 0
                    : "0.8rem 1rem",
                  borderRadius: msg.images?.length ? "0.875rem" : "1.25rem",
                  backgroundColor: msg.role === "user" ? "#2a2a2d" : "transparent",
                  color: msg.role === "user" ? "white" : "var(--text-primary)",
                  wordBreak: "break-word",
                  lineHeight: msg.role === "assistant" ? "1.68" : "1.5",
                  fontSize: msg.role === "assistant" ? "1rem" : "0.975rem",
                  ...(msg.role === "user" ? { whiteSpace: "pre-wrap" as const } : {}),
                }}
              >
                {msg.content && (
                  <div style={msg.images?.length ? { marginBottom: "0.25rem" } : undefined}>
                    {isFormSubmission ? (
                      <SubmittedFormMessage message={msg} />
                    ) : msg.role === "assistant" ? (
                      <MarkdownRenderer content={msg.content} />
                    ) : (
                      msg.content
                    )}
                  </div>
                )}
                {renderImages(msg.images)}
                {renderAttachments(msg.role, msg.attachments)}
              </div>
            </div>
          );
        }

        if (item.kind === "streaming") {
          return (
            <div key={item.key} style={{ display: "flex", alignItems: "flex-start", width: "100%" }}>
              <div
                style={{
                  width: "100%",
                  padding: 0,
                  borderRadius: 0,
                  backgroundColor: "transparent",
                  color: "var(--text-primary)",
                  wordBreak: "break-word",
                  lineHeight: "1.68",
                  fontSize: "1rem",
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
