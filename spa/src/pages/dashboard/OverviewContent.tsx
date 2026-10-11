import { Link } from "react-router-dom";
import {
  ArrowRight,
  Bot,
  CheckCircle2,
  Circle,
  Database,
  MessageSquare,
  Plus,
  ShoppingBag,
  Sparkles,
  Workflow,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Page, PageActions, PageBody, PageDescription, PageHeader } from "../../components/layout";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../components/ui/card";
import { InlineEmptyState } from "../../components/ui/empty-state";
import { ProgressBar } from "../../components/ui/progress";
import type { AgentResponse } from "../../services/agents/AgentApiService";
import type { AutomationResponse } from "../../types/automation";
import type { ConnectorStatus, MCPConnection } from "../../types/connectors";
import type { ConversationResponse } from "../../types/conversation";
import type { KnowledgeBase } from "../../types/knowledge";
import { formatRelativeTime } from "../../utils/time";
import { formatCompactNumber } from "../../lib/utils";
import { changeLogEntries } from "../whats-new/whatsNewData";
import styles from "./Overview.module.css";

export interface DashboardData {
  agents: AgentResponse[];
  conversations: ConversationResponse[];
  automations: AutomationResponse[];
  knowledgeBases: KnowledgeBase[];
  connectors: ConnectorStatus[];
  mcpConnections: MCPConnection[];
}

const RECENT_LIMIT = 4;

export function OverviewContent({ data }: { data: DashboardData }) {
  const activeConversations = countRecentItems(data.conversations, activityDate);
  const activeAutomations = data.automations.filter((automation) => automation.status === "active").length;
  const enabledA2AAgents = data.agents.filter((agent) => agent.is_agent2agent_enabled).length;
  const totalKnowledgeVectors = data.knowledgeBases.reduce((sum, kb) => sum + kb.total_vectors, 0);
  const recentAgents = sortByActivity(data.agents, activityDate).slice(0, RECENT_LIMIT);
  const recentConversations = sortByActivity(data.conversations, activityDate).slice(0, RECENT_LIMIT);

  const stats: StatProps[] = [
    {
      label: "Agents",
      value: String(data.agents.length),
      detail: enabledA2AAgents ? `${enabledA2AAgents} open to A2A` : "None open to A2A",
      icon: Bot,
      to: "/dashboard/agents",
    },
    {
      label: "Active chats",
      value: String(activeConversations),
      detail: "Last 7 days",
      icon: MessageSquare,
      to: "/dashboard/conversations",
    },
    {
      label: "Automations",
      value: String(data.automations.length),
      detail: `${activeAutomations} active`,
      icon: Workflow,
      to: "/dashboard/automations",
    },
    {
      label: "Knowledge",
      value: String(data.knowledgeBases.length),
      detail: `${formatCompactNumber(totalKnowledgeVectors)} indexed vectors`,
      icon: Database,
      to: "/dashboard/knowledge-bases",
    },
  ];

  const connectedSystems =
    data.connectors.filter((connector) => connector.connected).length +
    data.mcpConnections.filter((connection) => connection.enabled && connection.oauth_connected).length;
  const steps: Step[] = [
    { label: "Create an agent", done: data.agents.length > 0, to: "/dashboard/agents/new" },
    { label: "Start a conversation", done: data.conversations.length > 0, to: "/dashboard/conversations" },
    { label: "Add knowledge", done: data.knowledgeBases.length > 0, to: "/dashboard/knowledge-bases" },
    { label: "Connect a system", done: connectedSystems > 0, to: "/dashboard/connectors" },
    { label: "Create an automation", done: data.automations.length > 0, to: "/dashboard/automations" },
  ];
  const stepsDone = steps.filter((step) => step.done).length;

  return (
    <Page>
      <PageHeader>
        <PageDescription>Your agents, conversations and automations at a glance.</PageDescription>
        <PageActions>
          <Button asChild variant="outline">
            <Link to="/dashboard/agents/marketplace">
              <ShoppingBag />
              Marketplace
            </Link>
          </Button>
          <Button asChild>
            <Link to="/dashboard/agents/new">
              <Plus />
              New agent
            </Link>
          </Button>
        </PageActions>
      </PageHeader>

      <PageBody>
        <section className={styles.stats} aria-label="Workspace summary">
          {stats.map((stat) => (
            <Stat key={stat.label} {...stat} />
          ))}
        </section>

        <div className={styles.columns}>
          {data.agents.length === 0 ? (
            <Card>
              <CardContent>
                <div className={styles.first}>
                  <span className={styles.firstIcon} aria-hidden="true">
                    <Bot />
                  </span>
                  <h2 className={styles.firstTitle}>Create your first agent</h2>
                  <p className={styles.firstText}>
                    Give it instructions, a model and the skills it needs. Add knowledge and connectors whenever you like.
                  </p>
                  <Button asChild>
                    <Link to="/dashboard/agents/new">
                      <Plus />
                      New agent
                    </Link>
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>Recent work</CardTitle>
                <CardDescription>Pick up where you left off.</CardDescription>
              </CardHeader>
              <CardContent className={styles.recent}>
                <RecentList
                  title="Agents"
                  viewAllTo="/dashboard/agents"
                  icon={Bot}
                  emptyText="No agents yet"
                  items={recentAgents.map((agent) => ({
                    id: agent.agent_id,
                    title: agent.agent_name,
                    subtitle: [agent.agent_provider, agent.agent_model].filter(Boolean).join(" · "),
                    to: `/dashboard/agents/${agent.agent_id}`,
                    date: activityDate(agent),
                  }))}
                />
                <RecentList
                  title="Conversations"
                  viewAllTo="/dashboard/conversations"
                  icon={MessageSquare}
                  emptyText="No conversations yet"
                  items={recentConversations.map((conversation) => ({
                    id: conversation.conversation_id,
                    title: conversation.title,
                    subtitle: getAgentName(data.agents, conversation.agent_id),
                    to: `/dashboard/conversations/${conversation.conversation_id}`,
                    date: activityDate(conversation),
                  }))}
                />
              </CardContent>
            </Card>
          )}

          <aside className={styles.side} aria-label="Setup and updates">
            {stepsDone < steps.length && <GettingStarted steps={steps} done={stepsDone} />}
            <LatestRelease />
          </aside>
        </div>
      </PageBody>
    </Page>
  );
}

function activityDate(item: { updated_at?: string | null; created_at?: string | null }): string | undefined {
  return item.updated_at || item.created_at || undefined;
}

function countRecentItems<T>(items: T[], getDate: (item: T) => string | undefined): number {
  const oneWeekAgo = new Date();
  oneWeekAgo.setDate(oneWeekAgo.getDate() - 7);
  return items.filter((item) => {
    const date = getDate(item);
    return date ? new Date(date) >= oneWeekAgo : false;
  }).length;
}

function sortByActivity<T>(items: T[], getDate: (item: T) => string | undefined): T[] {
  return [...items].sort((left, right) => {
    const leftTime = new Date(getDate(left) || 0).getTime();
    const rightTime = new Date(getDate(right) || 0).getTime();
    return rightTime - leftTime;
  });
}

function getAgentName(agents: AgentResponse[], agentId: string): string {
  return agents.find((agent) => agent.agent_id === agentId)?.agent_name || "Unknown agent";
}

interface StatProps {
  label: string;
  value: string;
  detail: string;
  icon: LucideIcon;
  to: string;
}

function Stat({ label, value, detail, icon: Icon, to }: StatProps) {
  return (
    <Link className={styles.stat} to={to}>
      <span className={styles.statIcon} aria-hidden="true">
        <Icon />
      </span>
      <span className={styles.statBody}>
        <span className={styles.statLabel}>{label}</span>
        <strong className={styles.statValue}>{value}</strong>
        <span className={styles.statDetail}>{detail}</span>
      </span>
    </Link>
  );
}

interface RecentItem {
  id: string;
  title: string;
  subtitle: string;
  to: string;
  date?: string;
}

function RecentList({
  title,
  viewAllTo,
  icon: Icon,
  items,
  emptyText,
}: {
  title: string;
  viewAllTo: string;
  icon: LucideIcon;
  items: RecentItem[];
  emptyText: string;
}) {
  return (
    <section className={styles.recentSection} aria-label={title}>
      <div className={styles.recentHeader}>
        <h3 className={styles.recentTitle}>{title}</h3>
        <Link className={styles.viewAll} to={viewAllTo}>
          View all
        </Link>
      </div>
      {items.length === 0 ? (
        <InlineEmptyState icon={Icon} title={emptyText} />
      ) : (
        <ul className={styles.rows}>
          {items.map((item) => (
            <li key={item.id}>
              <Link className={styles.row} to={item.to}>
                <span className={styles.rowIcon} aria-hidden="true">
                  <Icon />
                </span>
                <span className={styles.rowText}>
                  <span className={styles.rowTitle}>{item.title}</span>
                  <span className={styles.rowSubtitle}>{item.subtitle || "No details"}</span>
                </span>
                {item.date && (
                  <time className={styles.rowTime} dateTime={item.date}>
                    {formatRelativeTime(item.date)}
                  </time>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

interface Step {
  label: string;
  done: boolean;
  to: string;
}

function GettingStarted({ steps, done }: { steps: Step[]; done: number }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Getting started</CardTitle>
        <CardDescription>
          {done} of {steps.length} steps done
        </CardDescription>
      </CardHeader>
      <CardContent className={styles.steps}>
        <ProgressBar value={done} max={steps.length} showLabel={false} size="sm" />
        <ul className={styles.stepList}>
          {steps.map((step) => (
            <li key={step.label}>
              <Link className={step.done ? `${styles.step} ${styles.stepDone}` : styles.step} to={step.to}>
                {step.done ? <CheckCircle2 aria-hidden="true" /> : <Circle aria-hidden="true" />}
                <span>{step.label}</span>
                <span className={styles.srOnly}>{step.done ? "Done" : "To do"}</span>
              </Link>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function LatestRelease() {
  const release = changeLogEntries[0];
  if (!release) return null;
  return (
    <Card>
      <CardHeader>
        <div className={styles.releaseHeader}>
          <CardTitle>What's new</CardTitle>
          <Sparkles className={styles.releaseIcon} aria-hidden="true" />
        </div>
        <CardDescription>
          <time dateTime={release.date}>{formatDate(release.date)}</time>
        </CardDescription>
      </CardHeader>
      <CardContent className={styles.release}>
        <h3 className={styles.releaseTitle}>{release.title}</h3>
        <p className={styles.releaseSummary}>{release.summary}</p>
        <Link className={styles.viewAll} to="/dashboard/whats-new">
          View updates <ArrowRight aria-hidden="true" />
        </Link>
      </CardContent>
    </Card>
  );
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}
