import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Bot, MessageSquare, Wrench, Brain, Plus, ArrowRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Grid, Stack, Center } from "../../components/ui/grid";
import { agentApiService, type AgentResponse } from "../../services/agents/AgentApiService";
import { conversationApiService } from "../../services/conversations";
import type { ConversationResponse } from "../../types/conversation";

export function Overview() {
  const [agents, setAgents] = useState<AgentResponse[]>([]);
  const [conversations, setConversations] = useState<ConversationResponse[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadData = async () => {
      try {
        const [agentsData, conversationsData] = await Promise.all([
          agentApiService.listAgents(),
          conversationApiService.listConversations(),
        ]);
        setAgents(agentsData);
        setConversations(conversationsData.items);
      } catch (err) {
        console.error("Error loading data:", err);
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, []);

  // Calculate active conversations (updated within a week)
  const getActiveConversationsCount = (): number => {
    const oneWeekAgo = new Date();
    oneWeekAgo.setDate(oneWeekAgo.getDate() - 7);

    return conversations.filter((conv) => {
      const lastActivity = conv.updated_at || conv.created_at;
      return new Date(lastActivity) >= oneWeekAgo;
    }).length;
  };

  const getAgentName = (agentId: string): string => {
    const agent = agents.find((a) => a.agent_id === agentId);
    return agent?.agent_name || "Unknown Agent";
  };

  const stats = [
    {
      label: "Total Agents",
      value: agents.length,
      icon: Bot,
      color: "from-[var(--gradient-start)] to-[var(--gradient-mid)]",
    },
    {
      label: "Active Conversations",
      value: getActiveConversationsCount(),
      icon: MessageSquare,
      color: "from-emerald-500 to-teal-500",
    },
    {
      label: "Tools Configured",
      value: 0,
      icon: Wrench,
      color: "from-orange-500 to-amber-500",
    },
    {
      label: "Memory Blocks",
      value: 0,
      icon: Brain,
      color: "from-pink-500 to-rose-500",
    },
  ];

  if (loading) {
    return (
      <Center className="h-64">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--gradient-start)] border-t-transparent" />
      </Center>
    );
  }

  return (
    <Stack gap="lg">
      {/* Stats Grid */}
      <Grid cols={1} colsSm={2} colsLg={4} gap="md">
        {stats.map((stat) => (
          <Card key={stat.label}>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide">
                    {stat.label}
                  </p>
                  <p className="text-2xl font-bold text-[var(--text-primary)] mt-2">
                    {stat.value}
                  </p>
                </div>
                <div
                  className={`h-12 w-12 rounded-lg bg-gradient-to-br ${stat.color} flex items-center justify-center`}
                >
                  <stat.icon className="h-6 w-6 text-white" />
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </Grid>

      {/* Quick Actions */}
      <Grid cols={1} colsLg={2} gap="md">
        {/* Recent Agents */}
        <Card>
          <CardHeader style={{ display: "flex", flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
            <CardTitle>Recent Agents</CardTitle>
            <Link to="/dashboard/agents">
              <Button variant="ghost" size="sm">
                View All
                <ArrowRight className="h-4 w-4 ml-2" />
              </Button>
            </Link>
          </CardHeader>
          <CardContent>
            {agents.length === 0 ? (
              <Center style={{ padding: "4rem 0" }}>
                <Bot className="h-16 w-16 text-[var(--text-muted)]" style={{ marginBottom: "1rem" }} />
                <p style={{ color: "var(--text-muted)", marginBottom: "1.5rem" }}>No agents yet</p>
                <Link to="/dashboard/agents/new">
                  <Button>
                    <Plus className="h-4 w-4 mr-2" />
                    Create Your First Agent
                  </Button>
                </Link>
              </Center>
            ) : (
              <Stack gap="xs">
                {agents.slice(0, 5).map((agent) => (
                  <Link
                    key={agent.agent_id}
                    to={`/dashboard/agents/${agent.agent_id}`}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "1rem",
                      padding: "1rem",
                      borderRadius: "0.5rem",
                      transition: "background-color 0.2s",
                    }}
                    className="hover:bg-white/5"
                  >
                    <div
                      className="bg-gradient-to-br from-[var(--gradient-start)] to-[var(--gradient-mid)]"
                      style={{
                        height: "3rem",
                        width: "3rem",
                        borderRadius: "0.5rem",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                      }}
                    >
                      <Bot className="h-6 w-6 text-white" />
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p style={{ fontWeight: 500, color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {agent.agent_name}
                      </p>
                      <p style={{ fontSize: "0.875rem", color: "var(--text-muted)", marginTop: "0.25rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {agent.agent_provider}
                      </p>
                    </div>
                  </Link>
                ))}
              </Stack>
            )}
          </CardContent>
        </Card>

        {/* Recent Conversations */}
        <Card>
          <CardHeader style={{ display: "flex", flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
            <CardTitle>Recent Conversations</CardTitle>
            <Link to="/dashboard/conversations">
              <Button variant="ghost" size="sm">
                View All
                <ArrowRight className="h-4 w-4 ml-2" />
              </Button>
            </Link>
          </CardHeader>
          <CardContent>
            {conversations.length === 0 ? (
              <Center style={{ padding: "4rem 0" }}>
                <MessageSquare className="h-16 w-16 text-[var(--text-muted)]" style={{ marginBottom: "1rem" }} />
                <p style={{ color: "var(--text-muted)" }}>No conversations yet</p>
                <p style={{ fontSize: "0.875rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>
                  Start chatting with your agents
                </p>
              </Center>
            ) : (
              <Stack gap="xs">
                {conversations.slice(0, 5).map((conversation) => (
                  <Link
                    key={conversation.conversation_id}
                    to={`/dashboard/conversations/${conversation.conversation_id}`}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "1rem",
                      padding: "1rem",
                      borderRadius: "0.5rem",
                      transition: "background-color 0.2s",
                    }}
                    className="hover:bg-white/5"
                  >
                    <div
                      style={{
                        height: "3rem",
                        width: "3rem",
                        borderRadius: "0.5rem",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        background: "linear-gradient(to bottom right, #10b981, #14b8a6)",
                      }}
                    >
                      <MessageSquare className="h-6 w-6 text-white" />
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p style={{ fontWeight: 500, color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {conversation.title}
                      </p>
                      <p style={{ fontSize: "0.875rem", color: "var(--text-muted)", marginTop: "0.25rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {getAgentName(conversation.agent_id)}
                      </p>
                    </div>
                  </Link>
                ))}
              </Stack>
            )}
          </CardContent>
        </Card>
      </Grid>

      {/* Getting Started */}
      {agents.length === 0 && (
        <Card>
          <CardContent style={{ padding: "5rem 2rem" }}>
            <Center style={{ maxWidth: "42rem", margin: "0 auto" }}>
              <h2 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "1rem" }}>
                Welcome to InnoMight Labs!
              </h2>
              <p style={{ color: "var(--text-secondary)", marginBottom: "2rem", lineHeight: 1.6 }}>
                Get started by creating your first AI agent. You can customize its
                persona, configure memory blocks, and add tools to make it powerful.
              </p>
              <Link to="/dashboard/agents/new">
                <Button size="lg">
                  <Plus className="h-5 w-5 mr-2" />
                  Create Your First Agent
                </Button>
              </Link>
            </Center>
          </CardContent>
        </Card>
      )}
    </Stack>
  );
}
