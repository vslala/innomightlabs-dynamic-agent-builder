import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Bot, Plus, Trash2, Settings } from "lucide-react";
import { Card, CardContent } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";
import {
  agentApiService,
  type AgentResponse,
} from "../../services/agents/AgentApiService";

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
    return (
      <div className="flex items-center justify-center h-64">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--gradient-start)] border-t-transparent" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4">
        <p className="text-red-400">{error}</p>
        <Button onClick={loadAgents}>Try Again</Button>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[var(--text-secondary)] text-base">
            Create and manage your AI agents
          </p>
        </div>
        <Button onClick={() => navigate("/dashboard/agents/new")} size="lg">
          <Plus className="h-5 w-5 mr-2" />
          Create Agent
        </Button>
      </div>

      {/* Agents Grid */}
      {agents.length === 0 ? (
        <Card>
          <CardContent className="p-12">
            <div className="text-center">
              <Bot className="h-16 w-16 mx-auto text-[var(--text-muted)] mb-4" />
              <h3 className="text-lg font-medium text-[var(--text-primary)] mb-2">
                No agents yet
              </h3>
              <p className="text-[var(--text-muted)] mb-6 max-w-sm mx-auto">
                Create your first AI agent to get started. You can customize its
                persona and connect it to different LLM providers.
              </p>
              <Button onClick={() => navigate("/dashboard/agents/new")}>
                <Plus className="h-4 w-4 mr-2" />
                Create Your First Agent
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {agents.map((agent) => (
            <Card
              key={agent.agent_id}
              className="group hover:border-[var(--gradient-start)]/50 transition-all duration-200"
            >
              <CardContent className="p-6">
                <div className="flex items-start justify-between mb-5">
                  <div className="h-14 w-14 rounded-xl bg-gradient-to-br from-[var(--gradient-start)] to-[var(--gradient-mid)] flex items-center justify-center">
                    <Bot className="h-7 w-7 text-white" />
                  </div>
                  <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Link to={`/dashboard/agents/${agent.agent_id}`}>
                      <Button variant="ghost" size="icon" className="h-9 w-9">
                        <Settings className="h-4 w-4" />
                      </Button>
                    </Link>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-9 w-9 text-red-400 hover:text-red-300"
                      onClick={() => {
                        setSelectedAgent(agent);
                        setIsDeleteDialogOpen(true);
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>

                <Link to={`/dashboard/agents/${agent.agent_id}`}>
                  <h3 className="font-semibold text-lg text-[var(--text-primary)] mb-2 hover:text-[var(--gradient-start)] transition-colors">
                    {agent.agent_name}
                  </h3>
                </Link>
                <p className="text-sm text-[var(--text-muted)] line-clamp-2 mb-4 leading-relaxed">
                  {agent.agent_persona}
                </p>

                <div className="flex items-center gap-2 pt-2">
                  <span className="inline-flex items-center px-3 py-1.5 rounded-md text-xs font-medium bg-[var(--gradient-start)]/10 text-[var(--gradient-start)]">
                    {agent.agent_provider}
                  </span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Delete Confirmation Dialog */}
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
    </div>
  );
}
