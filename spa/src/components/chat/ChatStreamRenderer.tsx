import { Fragment, memo, useEffect, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { ExternalLink, Image as ImageIcon, Loader2, User, Wrench } from "lucide-react";
import { buildChatStreamRenderPlan } from '../../../packages/chat-stream-renderer/src';
import { AttachmentChip } from "./AttachmentChip";
import { InlineCanvasCard } from "./InlineCanvasCard";
import { ToolActivityCard } from "./ToolActivityCard";
import { ToolActivitySummary } from "./ToolActivitySummary";
import { AccordionPanel, MarkdownRenderer } from "../ui";
import { SubmittedFormMessage } from "./SubmittedFormMessage";
import { isSubmittedFormMessage } from "./submittedFormParser";
import { ConsentDecisionMessage } from "./consent/ConsentDecisionMessage";
import { isConsentDecisionMessage } from "./consent/consentDecisionParser";
import { authHeaders } from "../../services/http";
import { cn } from "../../lib/utils";
import type {
  AttachmentInfo,
  Message,
  MessageCanvasArtifact,
  MessageConsent,
  MessageImage,
  MessageReference,
  ToolActivity,
} from "../../types/message";
import styles from "./ChatStreamRenderer.module.css";

interface ChatStreamRendererProps {
  messages: Message[];
  streamingContent?: string;
  toolActivities?: ToolActivity[];
  statusMessage?: string | null;
  userPicture?: string;
  userName?: string;
  extraNode?: ReactNode;
  debugToolActivity?: boolean;
  onExpandCanvas?: (canvas: MessageCanvasArtifact) => void;
  /** The card for a consent a message raised; the page owns their state, since a card is decided from it. */
  renderConsent?: (consent: MessageConsent) => ReactNode;
}

// AccordionPanel takes styles, not classes; kept here so they are not rebuilt every render
const ACTIVITY_PANEL_STYLE: CSSProperties = {
  margin: "0.5rem 0",
  borderRadius: "0.75rem",
  borderColor: "var(--border-default)",
  backgroundColor: "var(--surface-subtle)",
};
const ACTIVITY_BODY_STYLE: CSSProperties = { padding: "0 0.75rem 0.75rem" };

function Attachments({ attachments, references }: { attachments?: AttachmentInfo[]; references?: MessageReference[] }) {
  if (!attachments?.length && !references?.length) {
    return null;
  }

  return (
    <div className={styles.attachments}>
      {attachments?.map((attachment, index) => (
        <AttachmentChip
          key={`${attachment.filename}-${index}`}
          filename={attachment.filename}
          size={attachment.size}
          readonly
        />
      ))}
      {references?.map((reference) => (
        <AttachmentChip key={`${reference.kind}-${reference.id}`} filename={reference.label || reference.kind} readonly />
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
        if (image.preview_data_url) {
          setFailed(false);
          setObjectUrl(image.preview_data_url);
          return;
        }
        setFailed(true);
        return;
      }

      setFailed(false);
      setObjectUrl(image.preview_data_url || null);

      try {
        if (!requiresAuthenticatedFetch(image.url)) {
          setObjectUrl(image.url);
          return;
        }

        const response = await fetch(image.url, {
          headers: authHeaders(),
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
  }, [image.preview_data_url, image.url]);

  const displayUrl = failed && image.preview_data_url ? image.preview_data_url : objectUrl;

  if (!displayUrl) {
    return (
      <div className={cn(styles.imageFrame, styles.imagePlaceholder)}>
        <ImageIcon />
        <div className={styles.imagePlaceholderText}>
          <div className={styles.imagePlaceholderTitle}>Image preview unavailable</div>
          The image file could not be loaded. It may still be processing or unavailable in storage.
        </div>
      </div>
    );
  }

  if (!objectUrl) {
    return (
      <div className={cn(styles.imageFrame, styles.imagePlaceholder)}>
        <Loader2 className={styles.spinner} />
      </div>
    );
  }

  return (
    <a href={displayUrl} target="_blank" rel="noreferrer" title={label} className={styles.imageFrame}>
      <img
        src={displayUrl}
        alt={label}
        loading="lazy"
        decoding="async"
        onError={() => setFailed(true)}
        className={styles.image}
      />
      <span className={styles.imageOpen}>
        <ExternalLink />
      </span>
    </a>
  );
}

function requiresAuthenticatedFetch(url: string): boolean {
  if (url.startsWith("/")) {
    return true;
  }

  try {
    const parsedUrl = new URL(url, window.location.origin);
    const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
    const parsedApiBaseUrl = new URL(apiBaseUrl, window.location.origin);
    return parsedUrl.origin === parsedApiBaseUrl.origin;
  } catch {
    return false;
  }
}

function Images({ images }: { images?: MessageImage[] }) {
  if (!images?.length) {
    return null;
  }

  return (
    <div className={styles.images}>
      {images.map((image) => <ImagePreview key={image.image_id} image={image} />)}
    </div>
  );
}

function UserAvatar({ picture, name }: { picture?: string; name?: string }) {
  if (picture) {
    return <img src={picture} alt={name || "User"} className={styles.avatar} />;
  }
  return (
    <div className={styles.avatar} aria-hidden="true">
      <User />
    </div>
  );
}

interface MessageRowProps {
  message: Message;
  userPicture?: string;
  userName?: string;
  onExpandCanvas?: (canvas: MessageCanvasArtifact) => void;
  renderConsent?: (consent: MessageConsent) => ReactNode;
}

function MessageRowView({ message, userPicture, userName, onExpandCanvas, renderConsent }: MessageRowProps) {
  const isUser = message.role === "user";
  const hasImages = Boolean(message.images?.length);

  return (
    <div className={cn(styles.row, isUser && styles.userRow)}>
      {isUser && <UserAvatar picture={userPicture} name={userName} />}
      <div className={cn(styles.bubble, isUser ? styles.user : styles.assistant, hasImages && styles.withImages)}>
        {message.content && (
          <div className={styles.content}>
            {isUser && isSubmittedFormMessage(message) ? (
              <SubmittedFormMessage message={message} />
            ) : isConsentDecisionMessage(message) ? (
              <ConsentDecisionMessage message={message} />
            ) : isUser ? (
              message.content
            ) : (
              <MarkdownRenderer content={message.content} />
            )}
          </div>
        )}
        <Images images={message.image_attachments} />
        <Images images={message.images} />
        {message.canvases?.map((canvas) => (
          <InlineCanvasCard key={canvas.artifact_id} canvas={canvas} onExpand={onExpandCanvas ?? noop} />
        ))}
        {message.consents?.map((consent) => (
          <Fragment key={consent.consent_id}>{renderConsent?.(consent)}</Fragment>
        ))}
        <Attachments attachments={message.attachments} references={message.references} />
      </div>
    </div>
  );
}

/**
 * A saved message only renders again when it changes, so a streaming reply re-renders itself and not the whole
 * transcript. `renderConsent` is rebuilt by the page on every render; only a message that raised a consent needs it.
 */
const MessageRow = memo(
  MessageRowView,
  (previous, next) =>
    previous.message === next.message &&
    previous.userPicture === next.userPicture &&
    previous.userName === next.userName &&
    previous.onExpandCanvas === next.onExpandCanvas &&
    (!next.message.consents?.length || previous.renderConsent === next.renderConsent),
);

function noop() {}

function ToolActivityList({ activities, debug }: { activities: ToolActivity[]; debug: boolean }) {
  if (!debug) {
    return <ToolActivitySummary activities={activities} />;
  }

  return (
    <AccordionPanel
      defaultOpen={false}
      title={
        <span className={styles.activityTitle}>
          <Wrench />
          Agent Activity
        </span>
      }
      trailing={
        <span className={styles.activityCount}>
          {activities.length} {activities.length === 1 ? "step" : "steps"}
        </span>
      }
      style={ACTIVITY_PANEL_STYLE}
      bodyStyle={ACTIVITY_BODY_STYLE}
    >
      <div className={styles.activityList}>
        {activities.map((activity) => <ToolActivityCard key={activity.id} activity={activity} />)}
      </div>
    </AccordionPanel>
  );
}

export function ChatStreamRenderer({
  messages,
  streamingContent,
  toolActivities = [],
  statusMessage,
  userPicture,
  userName,
  extraNode,
  debugToolActivity = false,
  onExpandCanvas,
  renderConsent,
}: ChatStreamRendererProps) {
  const plan = buildChatStreamRenderPlan({
    messages,
    getMessageKey: (message) => message.message_id,
    streamingContent,
    hasExtraNode: toolActivities.length > 0 || Boolean(statusMessage) || Boolean(extraNode),
  });

  return (
    <>
      {plan.map((item) => {
        if (item.kind === "message") {
          return (
            <MessageRow
              key={item.key}
              message={item.message}
              userPicture={userPicture}
              userName={userName}
              onExpandCanvas={onExpandCanvas}
              renderConsent={renderConsent}
            />
          );
        }

        if (item.kind === "streaming") {
          return (
            <div key={item.key} className={styles.row}>
              <div className={cn(styles.bubble, styles.assistant)}>
                <MarkdownRenderer content={item.content} isStreaming />
                <span className={styles.cursor} aria-hidden="true" />
              </div>
            </div>
          );
        }

        if (item.kind === "extra") {
          return (
            <div key={item.key} className={styles.extra}>
              {toolActivities.length > 0 && <ToolActivityList activities={toolActivities} debug={debugToolActivity} />}
              {statusMessage && (
                <div className={styles.status} role="status">
                  <Loader2 className={styles.smallSpinner} />
                  {statusMessage}
                </div>
              )}
              {extraNode}
            </div>
          );
        }

        return null;
      })}
    </>
  );
}
