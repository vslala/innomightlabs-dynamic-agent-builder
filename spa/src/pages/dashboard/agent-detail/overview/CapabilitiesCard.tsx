/**
 * Everything the agent can draw on, in one card: skills, knowledge bases, MCP tools and memory blocks. Each group
 * links to its own tab to manage it; an empty group is one line with the action that fills it.
 */

import type { ReactNode } from "react";
import { BookOpen, Database, Server, Wrench } from "lucide-react";

import { LinkButton, Spinner } from "../../../../components/ui";
import type { MemoryBlockResponse } from "../../../../services/memory";
import type { AgentMCPConnection } from "../../../../types/connectors";
import type { KnowledgeBase } from "../../../../types/knowledge";
import type { InstalledSkill } from "../../../../types/skills";
import { SHAREABLE_AUDIENCES } from "../audiences";
import { OverviewCard } from "./OverviewCard";
import type { Loaded } from "./useOverviewData";

interface Item {
  key: string;
  title: string;
  detail: string;
  /** A short state worth seeing at a glance ("Off"), or nothing. */
  flag?: string;
}

export function CapabilitiesCard({
  agentPath,
  skills,
  knowledgeBases,
  mcpConnections,
  memoryBlocks,
}: {
  /** `/dashboard/agents/:agentId`, the base of each group's tab. */
  agentPath: string;
  skills: Loaded<InstalledSkill[]>;
  knowledgeBases: Loaded<KnowledgeBase[]>;
  mcpConnections: Loaded<AgentMCPConnection[]>;
  memoryBlocks: Loaded<MemoryBlockResponse[]>;
}) {
  return (
    <OverviewCard id="agent-capabilities" title="What it can use">
      <Group
        icon={<Wrench />}
        title="Skills"
        to={`${agentPath}/skills`}
        loaded={skills}
        summarize={(all) => `${all.filter((skill) => skill.enabled).length} active`}
        items={(all) =>
          all
            .filter((skill) => skill.enabled)
            .map((skill) => ({ key: skill.installed_skill_id, title: skill.name, detail: skill.description }))
        }
        empty="Add skills so it can call tools, APIs and workflows."
        emptyAction="Add skills"
      />
      <Group
        icon={<BookOpen />}
        title="Knowledge"
        to={`${agentPath}/knowledge-bases`}
        loaded={knowledgeBases}
        summarize={(all) => `${all.length} linked`}
        items={(all) =>
          all.map((kb) => ({
            key: kb.kb_id,
            title: kb.name,
            detail: [`${kb.total_pages.toLocaleString()} pages`, kb.description].filter(Boolean).join(" · "),
          }))
        }
        empty="Link a knowledge base so it can answer from your own content."
        emptyAction="Link knowledge"
      />
      <Group
        icon={<Server />}
        title="MCP tools"
        to={`${agentPath}/mcp-tools`}
        loaded={mcpConnections}
        summarize={(all) => `${all.filter((connection) => connection.enabled).length} on`}
        items={(all) =>
          all.map((connection) => ({
            key: connection.mcp_id,
            title: connection.name,
            detail: [hostOf(connection.server_url), sharedWith(connection)].join(" · "),
            flag: connection.enabled ? undefined : "Off",
          }))
        }
        empty="Connect an MCP server to give it tools from other services."
        emptyAction="Add MCP tools"
      />
      <Group
        icon={<Database />}
        title="Memory"
        to={`${agentPath}/memory`}
        loaded={memoryBlocks}
        summarize={(all) => `${all.length} blocks`}
        items={(all) =>
          all.map((block) => ({
            key: block.block_name,
            title: block.block_name,
            detail: [`${block.word_count.toLocaleString()} of ${block.word_limit.toLocaleString()} words`, block.description]
              .filter(Boolean)
              .join(" · "),
            flag: block.capacity_percent >= 90 ? "Nearly full" : undefined,
          }))
        }
        empty="It keeps memory blocks once it starts chatting."
        emptyAction="Open memory"
      />
    </OverviewCard>
  );
}

function Group<T>({
  icon,
  title,
  to,
  loaded,
  summarize,
  items,
  empty,
  emptyAction,
}: {
  icon: ReactNode;
  title: string;
  to: string;
  loaded: Loaded<T[]>;
  summarize: (all: T[]) => string;
  items: (all: T[]) => Item[];
  empty: string;
  emptyAction: string;
}) {
  const shown = loaded.state === "ready" ? items(loaded.value) : [];

  return (
    <div className="agent-overview-group">
      <div className="agent-overview-group__head">
        <h3>
          {icon}
          {title}
          {loaded.state === "ready" && shown.length > 0 ? (
            <span className="agent-overview-group__count">{summarize(loaded.value)}</span>
          ) : null}
        </h3>
        <LinkButton to={to} variant="link" size="sm">
          Manage
        </LinkButton>
      </div>

      {loaded.state === "loading" ? (
        <p className="agent-overview-muted agent-overview-group__status">
          <Spinner size="sm" /> Loading…
        </p>
      ) : loaded.state === "failed" ? (
        <p className="agent-overview-muted agent-overview-group__status" role="alert">
          Couldn't load {title.toLowerCase()}. Open the tab to try again.
        </p>
      ) : shown.length === 0 ? (
        <div className="agent-overview-empty-line">
          <span>{empty}</span>
          <LinkButton to={to} variant="link" size="sm">
            {emptyAction}
          </LinkButton>
        </div>
      ) : (
        <ul className="agent-overview-items">
          {shown.map((item) => (
            <li key={item.key} className="agent-overview-items__item">
              <span className="agent-overview-items__icon" aria-hidden="true">
                {icon}
              </span>
              <span className="agent-overview-items__text">
                <strong>{item.title}</strong>
                {item.detail ? <small>{item.detail}</small> : null}
              </span>
              {item.flag ? <span className="agent-overview-items__flag">{item.flag}</span> : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

/** Who besides the owner gets this connector's tools. */
function sharedWith(connection: AgentMCPConnection): string {
  const audiences = SHAREABLE_AUDIENCES.filter((audience) => connection.sharing.available_to.includes(audience.kind));
  return audiences.length ? `Shared with ${audiences.map((audience) => audience.label.toLowerCase()).join(", ")}` : "Only you";
}
