import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Dialog, DialogContent, DialogDescription, DialogTitle, LoadingState, SearchInput } from "../ui";
import { AgentIcon } from "../AgentIcon";
import { agentApiService, type AgentResponse } from "../../services/agents/AgentApiService";
import { useFavoriteAgents } from "../../hooks/useFavoriteAgents";
import { agentSummary, matchesQuery, recentAgents, sortAgents, timeAgo } from "../../pages/dashboard/agentDiscovery";
import styles from "../../pages/dashboard/AgentsList.module.css";

const MAX_RESULTS = 8;
const RECENT_SIZE = 5;

interface AgentQuickSwitcherProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** ⌘K: jump to an agent from anywhere in the dashboard. */
export function AgentQuickSwitcher({ open, onOpenChange }: AgentQuickSwitcherProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={styles.switcher}>
        <DialogTitle className="sr-only">Jump to an agent</DialogTitle>
        <DialogDescription className="sr-only">
          Type to search your agents. Use the arrow keys to choose one and Enter to open it.
        </DialogDescription>
        {/* Mounted only while open, so it loads fresh agents and favorites each time */}
        <SwitcherBody close={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}

function SwitcherBody({ close }: { close: () => void }) {
  const navigate = useNavigate();
  const { favorites } = useFavoriteAgents();
  const [agents, setAgents] = useState<AgentResponse[] | null>(null);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);

  useEffect(() => {
    agentApiService.listAgents().then(setAgents, () => setAgents([]));
  }, []);

  const { sections, flat } = useMemo(() => {
    const all = agents ?? [];
    if (query.trim()) {
      const matches = sortAgents(all.filter((agent) => matchesQuery(agent, query)), "used").slice(0, MAX_RESULTS);
      return { sections: [{ heading: null, agents: matches }], flat: matches };
    }
    const starred = all.filter((agent) => favorites.has(agent.agent_id));
    const recent = recentAgents(all, RECENT_SIZE + starred.length).filter((agent) => !favorites.has(agent.agent_id)).slice(0, RECENT_SIZE);
    return {
      sections: [{ heading: "Favorites", agents: starred }, { heading: "Recent", agents: recent }].filter((s) => s.agents.length),
      flat: [...starred, ...recent],
    };
  }, [agents, favorites, query]);

  const open = (agent: AgentResponse) => {
    close();
    navigate(`/dashboard/agents/${agent.agent_id}`);
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((i) => Math.min(i + 1, flat.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (event.key === "Enter" && flat[active]) {
      open(flat[active]);
    }
  };

  let index = -1;
  return (
    <>
      <SearchInput
        autoFocus
        aria-label="Jump to an agent"
        placeholder="Jump to an agent…"
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setActive(0);
        }}
        onKeyDown={onKeyDown}
      />
      {agents === null ? (
        <LoadingState />
      ) : flat.length === 0 ? (
        <p className={styles.switcherHeading}>{query.trim() ? "No matches" : "Star or use an agent and it will show up here"}</p>
      ) : (
        <div className={styles.switcherList}>
          {sections.map((section) => (
            <div key={section.heading ?? "results"}>
              {section.heading && <h3 className={styles.switcherHeading}>{section.heading}</h3>}
              {section.agents.map((agent) => {
                index++;
                const isActive = index === active;
                return (
                  <Link
                    key={agent.agent_id}
                    to={`/dashboard/agents/${agent.agent_id}`}
                    className={`${styles.switcherRow} ${isActive ? styles.switcherRowActive : ""}`}
                    aria-current={isActive ? "true" : undefined}
                    onClick={close}
                    onMouseEnter={() => setActive(flat.indexOf(agent))}
                  >
                    <span className={styles.pillIcon}>
                      <AgentIcon name={agent.agent_name} className={styles.pillIconSvg} />
                    </span>
                    <span className={styles.switcherText}>
                      <span>{agent.agent_name}</span>
                      <span className={styles.switcherSummary}>{agentSummary(agent)}</span>
                    </span>
                    <span className={styles.pillMeta}>{agent.last_used_at ? timeAgo(agent.last_used_at) : ""}</span>
                  </Link>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
