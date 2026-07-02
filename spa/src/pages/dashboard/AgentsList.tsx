import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Bot, Plus, ShoppingBag, Trash2, Settings } from "lucide-react";
import {
  Card,
  CardContent,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  LoadingState,
  ErrorState,
  EmptyState,
} from "../../components/ui";
import {
  agentApiService,
  type AgentResponse,
} from "../../services/agents/AgentApiService";
import { Grid, Inline, Page, PageActions, PageBody, PageDescription, PageHeader, Stack } from "../../components/layout";

export function AgentsList() {
  const navigate = useNavigate();
  const [agents, setAgents] = useState<AgentResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<AgentResponse | null>(
    null
  );
  const [isDeleting, setIsDeleting] = useState(false);

  const loadAgents = async () => {
    try {
      setError(null);
      const data = await agentApiService.listAgents();
      setAgents(data);
    } catch (err) {
      setError("Failed to load agents. Please try again.");
      console.error("Error loading agents:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAgents();
  }, []);

  const handleDelete = async () => {
    if (!selectedAgent) return;
    setIsDeleting(true);
    try {
      await agentApiService.deleteAgent(selectedAgent.agent_id);
      setIsDeleteDialogOpen(false);
      setSelectedAgent(null);
      loadAgents();
    } catch (err) {
      console.error("Error deleting agent:", err);
    } finally {
      setIsDeleting(false);
    }
  };

  if (loading) {
    return <LoadingState />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={loadAgents} />;
  }

  return (
    <Page>
      <PageHeader>
        <PageDescription>Create and manage your AI agents</PageDescription>
        <PageActions>
          <Button variant="outline" onClick={() => navigate("/dashboard/agents/marketplace")} size="lg">
            <ShoppingBag className="h-5 w-5" />
            Marketplace
          </Button>
          <Button onClick={() => navigate("/dashboard/agents/new")} size="lg">
            <Plus className="h-5 w-5" />
            Create Agent
          </Button>
        </PageActions>
      </PageHeader>

      <PageBody>
        {agents.length === 0 ? (
          <EmptyState
            icon={Bot}
            title="No agents yet"
            description="Create your first AI agent to get started. You can customize its persona and connect it to different LLM providers."
            actionLabel="Create Your First Agent"
            onAction={() => navigate("/dashboard/agents/new")}
          />
        ) : (
          <Grid className="grid-cols-1 md:grid-cols-2 lg:grid-cols-3" gap="lg">
            {agents.map((agent) => (
              <Card
                key={agent.agent_id}
                className="group hover:border-[var(--gradient-start)]/50 transition-all duration-200"
              >
                <CardContent>
                  <Stack gap="md">
                    <Inline justify="space-between" align="flex-start" wrap={false}>
                  <div className="h-14 w-14 rounded-xl bg-gradient-to-br from-[var(--gradient-start)] to-[var(--gradient-mid)] flex items-center justify-center">
                    <Bot className="h-7 w-7 text-white" />
                  </div>
                  <Inline gap="xs" className="opacity-0 transition-opacity group-hover:opacity-100">
                    <Link to={`/dashboard/agents/${agent.agent_id}`}>
                      <Button variant="ghost" size="icon">
                        <Settings className="h-4 w-4" />
                      </Button>
                    </Link>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="text-red-400 hover:text-red-300"
                      onClick={() => {
                        setSelectedAgent(agent);
                        setIsDeleteDialogOpen(true);
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </Inline>
                    </Inline>

                    <Stack gap="xs">
                      <Link to={`/dashboard/agents/${agent.agent_id}`}>
                        <h3 className="text-lg font-semibold text-[var(--text-primary)] transition-colors hover:text-[var(--gradient-start)]">
                          {agent.agent_name}
                        </h3>
                      </Link>
                      <p className="line-clamp-2 text-sm leading-relaxed text-[var(--text-muted)]">
                        {agent.agent_persona}
                      </p>
                    </Stack>

                    <Inline gap="xs">
                  <span className="inline-flex items-center px-3 py-1.5 rounded-md text-xs font-medium bg-[var(--gradient-start)]/10 text-[var(--gradient-start)]">
                    {agent.agent_provider}
                  </span>
                    </Inline>
                  </Stack>
                </CardContent>
              </Card>
            ))}
          </Grid>
        )}
      </PageBody>

      <Dialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Agent</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete "{selectedAgent?.agent_name}"?
              This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsDeleteDialogOpen(false)}
              disabled={isDeleting}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={isDeleting}
            >
              {isDeleting ? "Deleting..." : "Delete Agent"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Page>
  );
}
