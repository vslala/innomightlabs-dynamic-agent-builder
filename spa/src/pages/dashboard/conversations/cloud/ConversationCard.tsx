import { createElement, useLayoutEffect, useRef } from "react";
import { ArrowRight, Loader2, Trash2 } from "lucide-react";
import { Button } from "../../../../components/ui/button";
import { LinkButton } from "../../../../components/ui/link-button";
import { Pill } from "../../../../components/ui/pill";
import { getAgentIcon } from "../../../../lib/agentIcons";
import type { ConversationResponse } from "../../../../types/conversation";
import { formatRelativeTime } from "../../../../utils/time";
import styles from "./ConversationCard.module.css";

const AGENT_PALETTE = [
  { bg: "rgba(87, 157, 255, 0.16)", fg: "#579dff" },
  { bg: "rgba(168, 130, 255, 0.16)", fg: "#a882ff" },
  { bg: "rgba(76, 217, 165, 0.16)", fg: "#4cd9a5" },
  { bg: "rgba(255, 179, 71, 0.16)", fg: "#ffb347" },
  { bg: "rgba(255, 122, 158, 0.16)", fg: "#ff7a9e" },
  { bg: "rgba(94, 219, 219, 0.16)", fg: "#5edbdb" },
];

/** Each agent keeps one colour, so the same agent reads the same everywhere. */
function agentColors(agentId: string) {
  let hash = 0;
  for (let i = 0; i < agentId.length; i++) hash = (hash * 31 + agentId.charCodeAt(i)) >>> 0;
  return AGENT_PALETTE[hash % AGENT_PALETTE.length];
}

const startedOn = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });

/** Where a card goes: centred on `left`, beside the title at `anchorY`, inside a cloud `boxHeight` tall. */
export interface CardPlacement {
  left: number;
  anchorY: number;
  width: number;
  boxHeight: number;
}

const GAP = 14;
const EDGE = 8;

interface ConversationCardProps {
  conversation: ConversationResponse;
  agentName: string;
  placement: CardPlacement;
  deleting: boolean;
  onDelete: () => void;
  onPointerEnter: () => void;
  onPointerLeave: () => void;
}

/** What a title in the cloud shows when it's hovered or held: who it's with, when, and what it's about. */
export function ConversationCard({
  conversation,
  agentName,
  placement,
  deleting,
  onDelete,
  onPointerEnter,
  onPointerLeave,
}: ConversationCardProps) {
  const colors = agentColors(conversation.agent_id);
  const lastActivity = conversation.updated_at ?? conversation.created_at;
  const card = useRef<HTMLElement>(null);

  // Its height is only known once it's drawn: put it below the title, or above if there's more room there, and
  // never let it run past the cloud's edges. This runs before the browser paints, so it never shows in the wrong place.
  useLayoutEffect(() => {
    const el = card.current;
    if (!el) return;
    const room = placement.boxHeight - EDGE * 2;
    el.style.maxHeight = `${room}px`;
    const height = Math.min(el.offsetHeight, room);
    const below = placement.boxHeight - placement.anchorY - GAP - EDGE;
    const above = placement.anchorY - GAP - EDGE;
    const top = below >= height || below >= above ? placement.anchorY + GAP : placement.anchorY - GAP - height;
    el.style.top = `${Math.min(Math.max(top, EDGE), placement.boxHeight - height - EDGE)}px`;
  }, [placement]);

  return (
    <section
      ref={card}
      className={styles.card}
      style={{ left: placement.left, width: placement.width }}
      aria-label={`Details for ${conversation.title}`}
      data-cloud-ignore
      onPointerEnter={onPointerEnter}
      onPointerLeave={onPointerLeave}
    >
      <Pill size="sm" className={styles.agent} style={{ backgroundColor: colors.bg, color: colors.fg }}>
        {createElement(getAgentIcon(agentName), { className: styles.agentIcon })}
        <span className={styles.agentName}>{agentName}</span>
      </Pill>
      <h3 className={styles.title}>{conversation.title}</h3>
      {conversation.description && <p className={styles.description}>{conversation.description}</p>}
      <dl className={styles.meta}>
        <div>
          <dt>Last active</dt>
          <dd>{formatRelativeTime(lastActivity)}</dd>
        </div>
        <div>
          <dt>Started</dt>
          <dd>{startedOn(conversation.created_at)}</dd>
        </div>
      </dl>
      <div className={styles.actions}>
        <LinkButton to={`/dashboard/conversations/${conversation.conversation_id}`} size="sm" className={styles.open}>
          Open <ArrowRight className="h-3.5 w-3.5" />
        </LinkButton>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          title="Delete conversation"
          aria-label={`Delete ${conversation.title}`}
          disabled={deleting}
          onClick={onDelete}
        >
          {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
        </Button>
      </div>
    </section>
  );
}
