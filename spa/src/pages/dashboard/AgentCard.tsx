import { Link } from "react-router-dom";
import { Settings, Star, Trash2 } from "lucide-react";
import { AgentIcon } from "../../components/AgentIcon";
import { Button, Pill } from "../../components/ui";
import type { AgentAccess, AgentAttachedCounts, AgentResponse } from "../../services/agents/AgentApiService";
import { agentSummary, ATTACHMENTS, timeAgo } from "./agentDiscovery";
import styles from "./AgentsList.module.css";

// Agents you don't own say how you reach them
const ACCESS_BADGES: Partial<Record<AgentAccess, string>> = { shared: "Shared with you", admin: "Admin view" };

interface AgentCardProps {
  agent: AgentResponse;
  /** Undefined until the counts load */
  attached?: AgentAttachedCounts;
  favorite: boolean;
  /** Disables the chat button while a new conversation is being created */
  starting: boolean;
  onChat: (agent: AgentResponse) => void;
  onToggleFavorite: (agentId: string) => void;
  onDelete: (agent: AgentResponse) => void;
}

export function AgentCard({ agent, attached, favorite, starting, onChat, onToggleFavorite, onDelete }: AgentCardProps) {
  const detailPath = `/dashboard/agents/${agent.agent_id}`;

  return (
    <article className={styles.card}>
      <div className={styles.cardHead}>
        <div className={styles.agentIcon}>
          <AgentIcon name={agent.agent_name} className={styles.agentIconSvg} />
        </div>
        <h3 className={styles.agentName}>
          {/* The link stretches over the whole card, so the card is the tap target */}
          <Link to={detailPath} className={styles.cardLink}>
            {agent.agent_name}
          </Link>
        </h3>
        <Button
          variant="ghost"
          size="icon"
          className={styles.cardAction}
          aria-label={favorite ? `Remove ${agent.agent_name} from favorites` : `Add ${agent.agent_name} to favorites`}
          aria-pressed={favorite}
          onClick={() => onToggleFavorite(agent.agent_id)}
        >
          <Star className={favorite ? styles.starOn : undefined} />
        </Button>
      </div>

      <p className={styles.agentSummary}>{agentSummary(agent)}</p>

      <div className={styles.cardFoot}>
        {ACCESS_BADGES[agent.access] && (
          <Pill size="sm" variant="secondary">
            {ACCESS_BADGES[agent.access]}
          </Pill>
        )}
        <span className={styles.providerBadge}>{agent.agent_provider}</span>
        {attached &&
          ATTACHMENTS.filter(({ key }) => attached[key] > 0).map(({ key, label, Icon }) => (
            <span key={key} className={styles.attached} title={label}>
              <Icon aria-hidden="true" />
              {attached[key]}
              <span className="sr-only"> {label.toLowerCase()}</span>
            </span>
          ))}
        <span className={styles.lastUsed}>{agent.last_used_at ? `Used ${timeAgo(agent.last_used_at)}` : "Not used yet"}</span>
        <span className={styles.cardActions}>
          <Button
            variant="ghost"
            size="icon"
            className={styles.cardAction}
            aria-label={`Start a new chat with ${agent.agent_name}`}
            disabled={starting}
            onClick={() => onChat(agent)}
          >
            <span aria-hidden="true">💬</span>
          </Button>
          <Link to={detailPath}>
            <Button variant="ghost" size="icon" className={styles.cardAction} aria-label={`Settings for ${agent.agent_name}`}>
              <Settings />
            </Button>
          </Link>
          {agent.access === "owner" && (
            <Button
              variant="ghost"
              size="icon"
              className={`${styles.cardAction} ${styles.deleteButton}`}
              aria-label={`Delete ${agent.agent_name}`}
              onClick={() => onDelete(agent)}
            >
              <Trash2 />
            </Button>
          )}
        </span>
      </div>
    </article>
  );
}
