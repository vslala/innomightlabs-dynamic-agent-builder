import { useEffect, useState } from "react";

import { LoadingState } from "../../components/ui/spinner";
import { agentApiService } from "../../services/agents/AgentApiService";
import { automationApiService } from "../../services/automations";
import { connectorApiService } from "../../services/connectors";
import { conversationApiService } from "../../services/conversations";
import { knowledgeApiService } from "../../services/knowledge";
import { userVisibleConversations } from "../../utils/conversations";
import { OverviewContent, type DashboardData } from "./OverviewContent";

export function Overview() {
  const [data, setData] = useState<DashboardData | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadData() {
      // One failing request leaves its part of the page empty rather than failing the whole overview.
      const [agents, conversations, automations, knowledge, connectors, mcp] = await Promise.allSettled([
        agentApiService.listAgents(),
        conversationApiService.listConversations(),
        automationApiService.listAutomations(),
        knowledgeApiService.listKnowledgeBases(),
        connectorApiService.listConnectors(),
        connectorApiService.listMCPConnections(),
      ]);

      if (cancelled) return;

      setData({
        agents: settledValue(agents, []),
        conversations: userVisibleConversations(
          settledValue(conversations, { items: [], next_cursor: null, has_more: false }).items
        ),
        automations: settledValue(automations, []),
        knowledgeBases: settledValue(knowledge, []),
        connectors: settledValue(connectors, []),
        mcpConnections: settledValue(mcp, []),
      });
    }

    void loadData();

    return () => {
      cancelled = true;
    };
  }, []);

  if (!data) {
    return (
      <div role="status" aria-label="Loading overview">
        <LoadingState />
      </div>
    );
  }

  return <OverviewContent data={data} />;
}

function settledValue<T>(result: PromiseSettledResult<T>, fallback: T): T {
  return result.status === "fulfilled" ? result.value : fallback;
}
