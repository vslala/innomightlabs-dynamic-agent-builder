import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Bot, MessageSquare, Wrench, Brain, Plus, ArrowRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Grid, Stack, Center } from "../../components/ui/grid";
import { getAgentService } from "../../services/agents";
import type { Agent, Conversation } from "../../types/agent";

export function Overview() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadData = async () => {
      const service = getAgentService();
      const [agentsData, conversationsData] = await Promise.all([
        service.getAgents(),
        service.getConversations(),
      ]);
      setAgents(agentsData);
      setConversations(conversationsData);
      setLoading(false);
    };

    loadData();
  }, []);

  const stats = [
    {
      label: "Total Agents",
      value: agents.length,
      icon: Bot,
      color: "from-[var(--gradient-start)] to-[var(--gradient-mid)]",
    },
    {
      label: "Active Conversations",
      value: conversations.filter((c) => c.messageCount > 0).length,
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
          <CardHeader className="flex flex-row items-center justify-between">
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
              <Center className="py-16">
                <Bot className="h-16 w-16 text-[var(--text-muted)] mb-4" />
                <p className="text-[var(--text-muted)] mb-6">No agents yet</p>
                <Link to="/dashboard/agents">
                  <Button>
                    <Plus className="h-4 w-4 mr-2" />
                    Create Your First Agent
                  </Button>
                </Link>
              </Center>
            ) : (
              <Stack gap="xs">
                {agents.slice(0, 3).map((agent) => (
                  <Link
                    key={agent.id}
                    to={`/dashboard/agents/${agent.id}`}
                    className="flex items-center gap-4 p-4 rounded-lg hover:bg-white/5 transition-colors"
                  >
                    <div className="h-12 w-12 rounded-lg bg-gradient-to-br from-[var(--gradient-start)] to-[var(--gradient-mid)] flex items-center justify-center">
                      <Bot className="h-6 w-6 text-white" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-[var(--text-primary)] truncate">
                        {agent.name}
                      </p>
                      <p className="text-sm text-[var(--text-muted)] truncate mt-1">
                        {agent.agentModel}
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
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Recent Conversations</CardTitle>
            <Link to="/dashboard/conversations">
              <Button variant="ghost" size="sm">
                View All
                <ArrowRight className="h-4 w-4 ml-2" />
              </Button>
            </Link>
          </CardHeader>
          <CardContent>
            {conversations.filter((c) => c.messageCount > 0).length === 0 ? (
              <Center className="py-16">
                <MessageSquare className="h-16 w-16 text-[var(--text-muted)] mb-4" />
                <p className="text-[var(--text-muted)]">No conversations yet</p>
                <p className="text-sm text-[var(--text-muted)] mt-2">
                  Start chatting with your agents
                </p>
              </Center>
            ) : (
              <Stack gap="xs">
                {conversations
                  .filter((c) => c.messageCount > 0)
                  .slice(0, 3)
                  .map((conv) => (
                    <Link
                      key={conv.id}
                      to={`/dashboard/conversations?agent=${conv.agentId}`}
                      className="flex items-center gap-4 p-4 rounded-lg hover:bg-white/5 transition-colors"
                    >
                      <div className="h-12 w-12 rounded-full bg-gradient-to-br from-emerald-500 to-teal-500 flex items-center justify-center">
                        <MessageSquare className="h-6 w-6 text-white" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-[var(--text-primary)] truncate">
                          {conv.agentName}
                        </p>
                        <p className="text-sm text-[var(--text-muted)] truncate mt-1">
                          {conv.lastMessage || "No messages"}
                        </p>
                      </div>
                      <span className="text-sm text-[var(--text-muted)]">
                        {conv.messageCount} msgs
                      </span>
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
          <CardContent className="py-20 px-8">
            <Center className="text-center max-w-2xl mx-auto">
              <h2 className="text-2xl font-bold text-[var(--text-primary)] mb-4">
                Welcome to InnoMight Labs!
              </h2>
              <p className="text-[var(--text-secondary)] mb-8 leading-relaxed">
                Get started by creating your first AI agent. You can customize its
                persona, configure memory blocks, and add tools to make it powerful.
              </p>
              <Link to="/dashboard/agents">
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
