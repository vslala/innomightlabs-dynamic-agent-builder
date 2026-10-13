import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import { ConfirmationDialog } from "../../../../components/ui/confirmation-dialog";
import { useMediaQuery } from "../../../../hooks/useMediaQuery";
import { agentDisplayName } from "../../../../services/builder/ila";
import type { AgentResponse } from "../../../../services/agents/AgentApiService";
import type { ConversationResponse } from "../../../../types/conversation";
import { arrange, heatColor, titleSize } from "./cloudMath";
import { ConversationCard, type CardPlacement } from "./ConversationCard";
import { useCloudMotion } from "./useCloudMotion";
import styles from "./ConversationCloud.module.css";

const CARD_WIDTH = 288;
const EDGE_GAP = 8;
/** How long the pointer rests on a title before its card opens, so passing over titles doesn't flicker. */
const HOVER_OPEN_MS = 90;
/** How long the card stays once the pointer leaves, so the pointer can cross over to it. */
const HOVER_CLOSE_MS = 250;
const LEGEND_STOPS = [0, 0.25, 0.5, 0.75, 1];

const lastActivity = (c: ConversationResponse) => new Date(c.updated_at ?? c.created_at).getTime();

interface OpenCard extends CardPlacement {
  id: string;
}

interface ConversationCloudProps {
  conversations: ConversationResponse[];
  agents: AgentResponse[];
  deletingId: string | null;
  emptyMessage: string;
  onDelete: (conversation: ConversationResponse) => Promise<void> | void;
}

/**
 * Conversations as a ball of titles you can turn in any direction. Newer ones are bigger and warmer (a heat map from
 * blue to red), hovering a title (or holding a finger on it) shows its details, and tapping it opens it.
 */
export function ConversationCloud({ conversations, agents, deletingId, emptyMessage, onDelete }: ConversationCloudProps) {
  const arranged = useMemo(() => arrange(conversations, lastActivity), [conversations]);
  const points = useMemo(() => arranged.map((a) => a.base), [arranged]);
  const itemEls = useRef<(HTMLAnchorElement | null)[]>([]);
  const reducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)");
  const [open, setOpen] = useState<OpenCard | null>(null);
  const [confirming, setConfirming] = useState<ConversationResponse | null>(null);
  const hoverTimer = useRef<number | undefined>(undefined);

  const openIndex = open ? arranged.findIndex((a) => a.item.conversation_id === open.id) : -1;
  const openItem = openIndex >= 0 ? arranged[openIndex].item : null;

  const hide = useCallback(() => {
    window.clearTimeout(hoverTimer.current);
    setOpen(null);
  }, []);

  const { boxRef, handlers, swallowClick, anchorOf, bringToFront } = useCloudMotion({
    points,
    itemEls,
    hold: openItem !== null,
    reducedMotion,
    onLongPress: (index) => show(index),
    onDragStart: () => hide(),
  });

  function show(index: number) {
    const anchor = anchorOf(index);
    const box = boxRef.current;
    const id = arranged[index]?.item.conversation_id;
    if (!anchor || !box || !id) return;
    const width = Math.min(CARD_WIDTH, box.clientWidth - EDGE_GAP * 2);
    const left = Math.min(Math.max(box.clientWidth / 2 + anchor.x, EDGE_GAP + width / 2), box.clientWidth - EDGE_GAP - width / 2);
    setOpen({ id, left, anchorY: box.clientHeight / 2 + anchor.y, width, boxHeight: box.clientHeight });
  }

  // A press anywhere outside the cloud closes the card (on touch there is no pointer leaving to do it).
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (!boxRef.current?.contains(event.target as Node)) hide();
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open, boxRef, hide]);

  const hoverOn = (index: number) => {
    window.clearTimeout(hoverTimer.current);
    hoverTimer.current = window.setTimeout(() => show(index), HOVER_OPEN_MS);
  };
  const hoverOff = () => {
    window.clearTimeout(hoverTimer.current);
    hoverTimer.current = window.setTimeout(hide, HOVER_CLOSE_MS);
  };

  if (arranged.length === 0) {
    return <div className={styles.empty}>{emptyMessage}</div>;
  }

  return (
    <div
      ref={boxRef}
      className={styles.cloud}
      role="group"
      aria-label="Conversations, newest first"
      {...handlers}
      onPointerDown={(event) => {
        if (!(event.target as HTMLElement).closest("[data-cloud-ignore], [data-index]")) hide();
        handlers.onPointerDown(event);
      }}
      onKeyDown={(event) => event.key === "Escape" && hide()}
      onBlur={(event) => {
        if (!boxRef.current?.contains(event.relatedTarget as Node | null)) hide();
      }}
    >
      {arranged.map(({ item, score }, index) => (
        <Link
          key={item.conversation_id}
          ref={(el) => {
            itemEls.current[index] = el;
          }}
          to={`/dashboard/conversations/${item.conversation_id}`}
          data-index={index}
          className={item.conversation_id === open?.id ? `${styles.item} ${styles.active}` : styles.item}
          style={
            {
              color: heatColor(score),
              "--size": `${titleSize(score, false)}px`,
              "--size-small": `${titleSize(score, true)}px`,
            } as CSSProperties
          }
          onPointerEnter={(event) => event.pointerType === "mouse" && hoverOn(index)}
          onPointerLeave={(event) => event.pointerType === "mouse" && hoverOff()}
          onFocus={(event) => {
            if (event.currentTarget.matches(":focus-visible")) bringToFront(index, () => show(index));
          }}
          onClick={(event) => {
            if (swallowClick()) event.preventDefault();
          }}
          onContextMenu={(event) => event.preventDefault()}
        >
          {item.title}
        </Link>
      ))}

      {open && openItem && (
        <ConversationCard
          conversation={openItem}
          agentName={agentDisplayName(agents, openItem.agent_id)}
          placement={open}
          deleting={deletingId === openItem.conversation_id}
          onDelete={() => setConfirming(openItem)}
          onPointerEnter={() => window.clearTimeout(hoverTimer.current)}
          onPointerLeave={hoverOff}
        />
      )}

      <div className={styles.legend} aria-hidden="true">
        <span>Older</span>
        <span
          className={styles.legendBar}
          style={{ background: `linear-gradient(90deg, ${LEGEND_STOPS.map(heatColor).join(", ")})` }}
        />
        <span>Recent</span>
      </div>
      <p className={styles.hint}>
        <span className={styles.hintMouse}>Drag to turn · hover for details · click to open</span>
        <span className={styles.hintTouch}>Drag to turn · hold for details · tap to open</span>
      </p>

      <ConfirmationDialog
        open={confirming !== null}
        onOpenChange={(next) => !next && setConfirming(null)}
        title="Delete conversation"
        description={`Delete "${confirming?.title ?? ""}"? This can't be undone.`}
        confirmText="Delete"
        variant="destructive"
        loading={confirming !== null && deletingId === confirming.conversation_id}
        loadingText="Deleting..."
        onConfirm={async () => {
          if (!confirming) return;
          await onDelete(confirming);
          setConfirming(null);
          hide();
        }}
      />
    </div>
  );
}
