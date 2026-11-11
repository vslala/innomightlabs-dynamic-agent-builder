/** The agent's runtime settings and record, at a glance. */

import type { ReactNode } from "react";

import { CopyButton } from "../../../../components/ui";
import type { AgentResponse } from "../../../../services/agents/AgentApiService";
import { OverviewCard } from "./OverviewCard";

export function DetailsCard({ agent }: { agent: AgentResponse }) {
  return (
    <OverviewCard id="agent-details" title="Details">
      <dl className="agent-overview-details">
        <Detail label="Provider">{agent.agent_provider}</Detail>
        <Detail label="Model">{agent.agent_model || "Default"}</Detail>
        <Detail label="Architecture">
          <code>{agent.agent_architecture}</code>
        </Detail>
        <Detail label="Created">{formatDate(agent.created_at)}</Detail>
        <Detail label="Updated">{agent.updated_at ? formatDate(agent.updated_at) : "Not updated"}</Detail>
        <Detail label="Agent id">
          <code title={agent.agent_id}>{agent.agent_id.slice(0, 8)}…</code>
          <CopyButton value={agent.agent_id} label="Copy agent id" />
        </Detail>
      </dl>
    </OverviewCard>
  );
}

function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}
