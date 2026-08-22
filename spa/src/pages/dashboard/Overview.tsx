import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Archive,
  ArrowRight,
  Bot,
  BookOpen,
  CheckCircle2,
  CircleAlert,
  Database,
  FileText,
  MessageSquare,
  Network,
  Plug,
  Plus,
  Rocket,
  ShoppingBag,
  Sparkles,
  Workflow,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Button } from "../../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../components/ui/card";
import { agentApiService, type AgentResponse } from "../../services/agents/AgentApiService";
import { artifactApiService, type ArtifactResponse } from "../../services/artifacts";
import { automationApiService } from "../../services/automations";
import { connectorApiService } from "../../services/connectors";
import { conversationApiService } from "../../services/conversations";
import { knowledgeApiService } from "../../services/knowledge";
import type { AutomationResponse } from "../../types/automation";
import type { ConnectorStatus, MCPConnection } from "../../types/connectors";
import type { ConversationResponse } from "../../types/conversation";
import type { KnowledgeBase } from "../../types/knowledge";
import { userVisibleConversations } from "../../utils/conversations";
import { changeLogEntries } from "./whatsNewData";
import "./Overview.css";

interface DashboardData {
  agents: AgentResponse[];
  conversations: ConversationResponse[];
  automations: AutomationResponse[];
  knowledgeBases: KnowledgeBase[];
  connectors: ConnectorStatus[];
  mcpConnections: MCPConnection[];
  artifacts: ArtifactResponse[];
}

const emptyDashboardData: DashboardData = {
  agents: [],
  conversations: [],
  automations: [],
  knowledgeBases: [],
  connectors: [],
  mcpConnections: [],
  artifacts: [],
};

export function Overview() {
  const [data, setData] = useState<DashboardData>(emptyDashboardData);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function loadData() {
      setLoading(true);
      const [
        agentsResult,
        conversationsResult,
        automationsResult,
        knowledgeResult,
        connectorsResult,
        mcpResult,
        artifactsResult,
      ] = await Promise.allSettled([
        agentApiService.listAgents(),
        conversationApiService.listConversations(),
        automationApiService.listAutomations(),
        knowledgeApiService.listKnowledgeBases(),
        connectorApiService.listConnectors(),
        connectorApiService.listMCPConnections(),
        artifactApiService.listArtifacts(25),
      ]);

      if (cancelled) return;

      setData({
        agents: settledValue(agentsResult, []),
        conversations: userVisibleConversations(
          settledValue(conversationsResult, { items: [], next_cursor: null, has_more: false }).items
        ),
        automations: settledValue(automationsResult, []),
        knowledgeBases: settledValue(knowledgeResult, []),
        connectors: settledValue(connectorsResult, []),
        mcpConnections: settledValue(mcpResult, []),
        artifacts: settledValue(artifactsResult, { items: [] }).items,
      });
      setLoading(false);
    }

    void loadData();

    return () => {
      cancelled = true;
    };
  }, []);

  const activeConversations = useMemo(
    () => countRecentItems(data.conversations, (conversation) => conversation.updated_at || conversation.created_at),
    [data.conversations]
  );
  const activeAutomations = data.automations.filter((automation) => automation.status === "active").length;
  const enabledA2AAgents = data.agents.filter((agent) => agent.is_agent2agent_enabled).length;
  const connectedSystems =
    data.connectors.filter((connector) => connector.connected).length +
    data.mcpConnections.filter((connection) => connection.enabled && connection.oauth_connected).length;
  const totalKnowledgeVectors = data.knowledgeBases.reduce((sum, kb) => sum + kb.total_vectors, 0);
  const recentAgents = sortByActivity(data.agents, (agent) => agent.updated_at || agent.created_at).slice(0, 4);
  const recentConversations = sortByActivity(
    data.conversations,
    (conversation) => conversation.updated_at || conversation.created_at
  ).slice(0, 4);
  const latestRelease = changeLogEntries[0];

  const metrics: MetricCardProps[] = [
    {
      label: "Agents",
      value: data.agents.length,
      detail: `${enabledA2AAgents} discoverable through A2A`,
      icon: Bot,
      tone: "blue",
    },
    {
      label: "Active chats",
      value: activeConversations,
      detail: "Updated in the last 7 days",
      icon: MessageSquare,
      tone: "green",
    },
    {
      label: "Automations",
      value: data.automations.length,
      detail: `${activeAutomations} currently active`,
      icon: Workflow,
      tone: "orange",
    },
    {
      label: "Knowledge",
      value: data.knowledgeBases.length,
      detail: `${formatCompactNumber(totalKnowledgeVectors)} indexed vectors`,
      icon: Database,
      tone: "pink",
    },
  ];

  const featureCards: FeatureCardProps[] = [
    {
      title: "Build an agent",
      description: "Create a focused assistant with model settings, instructions, skills, memory, and knowledge.",
      to: "/dashboard/agents/new",
      icon: Bot,
      action: "Create",
    },
    {
      title: "Browse agent templates",
      description: "Import reusable agents from the marketplace and configure only the secrets you own.",
      to: "/dashboard/agents/marketplace",
      icon: ShoppingBag,
      action: "Browse",
    },
    {
      title: "Automate workflows",
      description: "Chain agent calls, skill actions, schedules, webhooks, and run history into repeatable processes.",
      to: "/dashboard/automations",
      icon: Workflow,
      action: "Open",
    },
    {
      title: "Ground answers",
      description: "Upload files or crawl sites into knowledge bases that agents can retrieve from during work.",
      to: "/dashboard/knowledge-bases",
      icon: BookOpen,
      action: "Add knowledge",
    },
    {
      title: "Share artifacts",
      description: "Keep generated reports, files, images, and HTML outputs in a central user-owned library.",
      to: "/dashboard/artifacts",
      icon: Archive,
      action: "View",
    },
    {
      title: "Connect systems",
      description: "Authorize provider connectors and MCP servers so agents can work with external tools.",
      to: "/dashboard/connectors",
      icon: Plug,
      action: "Connect",
    },
    {
      title: "Expose Agent2Agent",
      description: "Publish agent cards through the custom registry and let trusted clients send A2A messages.",
      to: "/docs/agent-to-agent",
      icon: Network,
      action: "Docs",
    },
    {
      title: "Track product updates",
      description: "See new capabilities as they ship and find workflows worth trying in your workspace.",
      to: "/dashboard/whats-new",
      icon: Sparkles,
      action: "What's new",
    },
  ];

  const setupItems: SetupItemProps[] = [
    {
      label: "Create an agent",
      complete: data.agents.length > 0,
      to: "/dashboard/agents/new",
    },
    {
      label: "Start a conversation",
      complete: data.conversations.length > 0,
      to: "/dashboard/conversations",
    },
    {
      label: "Add knowledge",
      complete: data.knowledgeBases.length > 0,
      to: "/dashboard/knowledge-bases",
    },
    {
      label: "Connect a system",
      complete: connectedSystems > 0,
      to: "/dashboard/connectors",
    },
    {
      label: "Create an automation",
      complete: data.automations.length > 0,
      to: "/dashboard/automations",
    },
  ];

  if (loading) {
    return (
      <div className="overview__loading">
        <div />
      </div>
    );
  }

  return (
    <div className="overview">
      <section className="overview__top-grid">
        <Card className="overview__command-panel">
          <CardHeader>
            <div className="overview__eyebrow">Workspace</div>
            <CardTitle className="overview__command-title">Build, run, and share agent workflows</CardTitle>
            <CardDescription>
              Start from an agent, connect it to tools and knowledge, then turn repeatable work into automations and artifacts.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overview__quick-actions">
              <Button asChild>
                <Link to="/dashboard/agents/new">
                  <Plus />
                  New agent
                </Link>
              </Button>
              <Button asChild variant="outline">
                <Link to="/dashboard/agents/marketplace">
                  <ShoppingBag />
                  Marketplace
                </Link>
              </Button>
              <Button asChild variant="outline">
                <Link to="/dashboard/automations">
                  <Workflow />
                  Automations
                </Link>
              </Button>
              <Button asChild variant="outline">
                <Link to="/dashboard/knowledge-bases">
                  <BookOpen />
                  Knowledge
                </Link>
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card className="overview__release-panel">
          <CardHeader>
            <div className="overview__panel-heading">
              <div>
                <CardTitle>What's New</CardTitle>
                <CardDescription>{formatDate(latestRelease.date)}</CardDescription>
              </div>
              <Sparkles className="overview__panel-icon" />
            </div>
          </CardHeader>
          <CardContent>
            <h3>{latestRelease.title}</h3>
            <p>{latestRelease.summary}</p>
            <div className="overview__release-items">
              {latestRelease.items.slice(0, 2).map((item) => (
                <div key={item.title}>
                  <span>{item.title}</span>
                  <small>{item.category}</small>
                </div>
              ))}
            </div>
            <Button asChild variant="ghost" size="sm">
              <Link to="/dashboard/whats-new">
                View updates
                <ArrowRight />
              </Link>
            </Button>
          </CardContent>
        </Card>
      </section>

      <section className="overview__metric-grid" aria-label="Workspace metrics">
        {metrics.map((metric) => (
          <MetricCard key={metric.label} {...metric} />
        ))}
      </section>

      <section className="overview__body-grid">
        <div className="overview__main-column">
          <Card>
            <CardHeader>
              <CardTitle>Explore the Platform</CardTitle>
              <CardDescription>Entry points for the work users can create from this dashboard.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="overview__feature-grid">
                {featureCards.map((feature) => (
                  <FeatureCard key={feature.title} {...feature} />
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Recent Work</CardTitle>
              <CardDescription>Continue from the agents and conversations that changed most recently.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="overview__recent-grid">
                <RecentList
                  title="Agents"
                  emptyTitle="No agents yet"
                  emptyAction="Create agent"
                  emptyTo="/dashboard/agents/new"
                  viewAllTo="/dashboard/agents"
                  icon={Bot}
                  items={recentAgents.map((agent) => ({
                    id: agent.agent_id,
                    title: agent.agent_name,
                    subtitle: [agent.agent_provider, agent.agent_model].filter(Boolean).join(" · "),
                    to: `/dashboard/agents/${agent.agent_id}`,
                    date: agent.updated_at || agent.created_at,
                  }))}
                />
                <RecentList
                  title="Conversations"
                  emptyTitle="No conversations yet"
                  emptyAction="Open conversations"
                  emptyTo="/dashboard/conversations"
                  viewAllTo="/dashboard/conversations"
                  icon={MessageSquare}
                  items={recentConversations.map((conversation) => ({
                    id: conversation.conversation_id,
                    title: conversation.title,
                    subtitle: getAgentName(data.agents, conversation.agent_id),
                    to: `/dashboard/conversations/${conversation.conversation_id}`,
                    date: conversation.updated_at || conversation.created_at,
                  }))}
                />
              </div>
            </CardContent>
          </Card>
        </div>

        <aside className="overview__side-column">
          <Card>
            <CardHeader>
              <CardTitle>Setup Health</CardTitle>
              <CardDescription>Suggested steps based on this workspace.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="overview__setup-list">
                {setupItems.map((item) => (
                  <SetupItem key={item.label} {...item} />
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Workspace Inventory</CardTitle>
              <CardDescription>Assets available to agents and automations.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="overview__inventory">
                <InventoryRow label="Artifacts" value={data.artifacts.length} icon={FileText} to="/dashboard/artifacts" />
                <InventoryRow label="Connected systems" value={connectedSystems} icon={Plug} to="/dashboard/connectors" />
                <InventoryRow label="A2A-enabled agents" value={enabledA2AAgents} icon={Network} to="/docs/agent-to-agent" />
                <InventoryRow label="Active automations" value={activeAutomations} icon={Rocket} to="/dashboard/automations" />
              </div>
            </CardContent>
          </Card>
        </aside>
      </section>
    </div>
  );
}

function settledValue<T>(result: PromiseSettledResult<T>, fallback: T): T {
  return result.status === "fulfilled" ? result.value : fallback;
}

function countRecentItems<T>(items: T[], getDate: (item: T) => string | null | undefined): number {
  const oneWeekAgo = new Date();
  oneWeekAgo.setDate(oneWeekAgo.getDate() - 7);
  return items.filter((item) => {
    const date = getDate(item);
    return date ? new Date(date) >= oneWeekAgo : false;
  }).length;
}

function sortByActivity<T>(items: T[], getDate: (item: T) => string | null | undefined): T[] {
  return [...items].sort((left, right) => {
    const leftTime = new Date(getDate(left) || 0).getTime();
    const rightTime = new Date(getDate(right) || 0).getTime();
    return rightTime - leftTime;
  });
}

function getAgentName(agents: AgentResponse[], agentId: string): string {
  return agents.find((agent) => agent.agent_id === agentId)?.agent_name || "Unknown agent";
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatCompactNumber(value: number): string {
  return Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

interface MetricCardProps {
  label: string;
  value: number;
  detail: string;
  icon: LucideIcon;
  tone: "blue" | "green" | "orange" | "pink";
}

function MetricCard({ label, value, detail, icon: Icon, tone }: MetricCardProps) {
  return (
    <Card className={`overview__metric-card overview__metric-card--${tone}`}>
      <div className="overview__metric-icon">
        <Icon />
      </div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <p>{detail}</p>
      </div>
    </Card>
  );
}

interface FeatureCardProps {
  title: string;
  description: string;
  to: string;
  icon: LucideIcon;
  action: string;
}

function FeatureCard({ title, description, to, icon: Icon, action }: FeatureCardProps) {
  return (
    <Link className="overview__feature-card" to={to}>
      <div className="overview__feature-icon">
        <Icon />
      </div>
      <div>
        <strong>{title}</strong>
        <p>{description}</p>
      </div>
      <span>
        {action}
        <ArrowRight />
      </span>
    </Link>
  );
}

interface RecentListItem {
  id: string;
  title: string;
  subtitle: string;
  to: string;
  date?: string | null;
}

interface RecentListProps {
  title: string;
  emptyTitle: string;
  emptyAction: string;
  emptyTo: string;
  viewAllTo: string;
  icon: LucideIcon;
  items: RecentListItem[];
}

function RecentList({ title, emptyTitle, emptyAction, emptyTo, viewAllTo, icon: Icon, items }: RecentListProps) {
  return (
    <div className="overview__recent-list">
      <div className="overview__recent-header">
        <h3>{title}</h3>
        <Link to={viewAllTo}>View all</Link>
      </div>
      {items.length ? (
        items.map((item) => (
          <Link key={item.id} className="overview__recent-item" to={item.to}>
            <div>
              <Icon />
            </div>
            <span>
              <strong>{item.title}</strong>
              <small>{item.subtitle || "No details"}</small>
            </span>
            <time>{item.date ? formatDate(item.date) : ""}</time>
          </Link>
        ))
      ) : (
        <div className="overview__empty-panel">
          <Icon />
          <strong>{emptyTitle}</strong>
          <Button asChild variant="outline" size="sm">
            <Link to={emptyTo}>{emptyAction}</Link>
          </Button>
        </div>
      )}
    </div>
  );
}

interface SetupItemProps {
  label: string;
  complete: boolean;
  to: string;
}

function SetupItem({ label, complete, to }: SetupItemProps) {
  return (
    <Link className="overview__setup-item" to={to}>
      <div className={complete ? "overview__setup-icon overview__setup-icon--done" : "overview__setup-icon"}>
        {complete ? <CheckCircle2 /> : <CircleAlert />}
      </div>
      <span>{label}</span>
      <small>{complete ? "Ready" : "Open"}</small>
    </Link>
  );
}

interface InventoryRowProps {
  label: string;
  value: number;
  icon: LucideIcon;
  to: string;
}

function InventoryRow({ label, value, icon: Icon, to }: InventoryRowProps) {
  return (
    <Link className="overview__inventory-row" to={to}>
      <Icon />
      <span>{label}</span>
      <strong>{value}</strong>
    </Link>
  );
}
