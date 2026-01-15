import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
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
  DialogTrigger,
} from "../../components/ui/dialog";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Textarea } from "../../components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../components/ui/select";
import { getAgentService } from "../../services/agents";
import type { Agent, AgentModel } from "../../types/agent";

const AGENT_MODELS: { value: AgentModel; label: string; description: string }[] = [
  {
    value: "krishna-mini",
    label: "Krishna Mini",
    description: "Fast and efficient for simple tasks",
  },
  {
    value: "krishna-memgpt",
    label: "Krishna MemGPT",
    description: "Advanced memory-augmented agent",
  },
];

const LLM_PROVIDERS = [
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "google", label: "Google" },
];

export function AgentsList() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [formData, setFormData] = useState({
    name: "",
    persona: "",
    agentModel: "krishna-mini" as AgentModel,
    llmProvider: "openai",
    llmModel: "gpt-4",
    llmApiKey: "",
  });

  const loadAgents = async () => {
    const service = getAgentService();
    const data = await service.getAgents();
    setAgents(data);
    setLoading(false);
  };

  useEffect(() => {
    loadAgents();
  }, []);

  const resetForm = () => {
    setFormData({
      name: "",
      persona: "",
      agentModel: "krishna-mini",
      llmProvider: "openai",
      llmModel: "gpt-4",
      llmApiKey: "",
    });
  };

  const handleCreate = async () => {
    const service = getAgentService();
    await service.createAgent({
      name: formData.name,
      persona: formData.persona,
      agentModel: formData.agentModel,
      llmConfig: {
        provider: formData.llmProvider,
        model: formData.llmModel,
        apiKey: formData.llmApiKey,
      },
    });
    setIsCreateDialogOpen(false);
    resetForm();
    loadAgents();
  };

  const handleDelete = async () => {
    if (!selectedAgent) return;
    const service = getAgentService();
    await service.deleteAgent(selectedAgent.id);
    setIsDeleteDialogOpen(false);
    setSelectedAgent(null);
    loadAgents();
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--gradient-start)] border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[var(--text-secondary)]">
            Create and manage your AI agents
          </p>
        </div>
        <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="h-4 w-4 mr-2" />
              Create Agent
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-lg">
            <DialogHeader>
              <DialogTitle>Create New Agent</DialogTitle>
              <DialogDescription>
                Configure your AI agent's identity and capabilities
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="name">Agent Name</Label>
                <Input
                  id="name"
                  placeholder="My Assistant"
                  value={formData.name}
                  onChange={(e) =>
                    setFormData({ ...formData, name: e.target.value })
                  }
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="persona">Persona</Label>
                <Textarea
                  id="persona"
                  placeholder="You are a helpful assistant that specializes in..."
                  value={formData.persona}
                  onChange={(e) =>
                    setFormData({ ...formData, persona: e.target.value })
                  }
                  rows={3}
                />
              </div>

              <div className="space-y-2">
                <Label>Agent Architecture</Label>
                <Select
                  value={formData.agentModel}
                  onValueChange={(value: AgentModel) =>
                    setFormData({ ...formData, agentModel: value })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {AGENT_MODELS.map((model) => (
                      <SelectItem key={model.value} value={model.value}>
                        <div>
                          <div className="font-medium">{model.label}</div>
                          <div className="text-xs text-[var(--text-muted)]">
                            {model.description}
                          </div>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="border-t border-[var(--border-subtle)] pt-4">
                <p className="text-sm font-medium text-[var(--text-secondary)] mb-3">
                  LLM Configuration
                </p>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Provider</Label>
                    <Select
                      value={formData.llmProvider}
                      onValueChange={(value) =>
                        setFormData({ ...formData, llmProvider: value })
                      }
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {LLM_PROVIDERS.map((provider) => (
                          <SelectItem key={provider.value} value={provider.value}>
                            {provider.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="llmModel">Model</Label>
                    <Input
                      id="llmModel"
                      placeholder="gpt-4"
                      value={formData.llmModel}
                      onChange={(e) =>
                        setFormData({ ...formData, llmModel: e.target.value })
                      }
                    />
                  </div>
                </div>

                <div className="space-y-2 mt-4">
                  <Label htmlFor="apiKey">API Key</Label>
                  <Input
                    id="apiKey"
                    type="password"
                    placeholder="sk-..."
                    value={formData.llmApiKey}
                    onChange={(e) =>
                      setFormData({ ...formData, llmApiKey: e.target.value })
                    }
                  />
                </div>
              </div>
            </div>

            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setIsCreateDialogOpen(false)}
              >
                Cancel
              </Button>
              <Button
                onClick={handleCreate}
                disabled={!formData.name || !formData.persona}
              >
                Create Agent
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
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
                persona, memory, and tools.
              </p>
              <Button onClick={() => setIsCreateDialogOpen(true)}>
                <Plus className="h-4 w-4 mr-2" />
                Create Your First Agent
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {agents.map((agent) => (
            <Card
              key={agent.id}
              className="group hover:border-[var(--gradient-start)]/50 transition-all duration-200"
            >
              <CardContent className="p-5">
                <div className="flex items-start justify-between mb-4">
                  <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-[var(--gradient-start)] to-[var(--gradient-mid)] flex items-center justify-center">
                    <Bot className="h-6 w-6 text-white" />
                  </div>
                  <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Link to={`/dashboard/agents/${agent.id}`}>
                      <Button variant="ghost" size="icon" className="h-8 w-8">
                        <Settings className="h-4 w-4" />
                      </Button>
                    </Link>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-red-400 hover:text-red-300"
                      onClick={() => {
                        setSelectedAgent(agent);
                        setIsDeleteDialogOpen(true);
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>

                <Link to={`/dashboard/agents/${agent.id}`}>
                  <h3 className="font-semibold text-[var(--text-primary)] mb-1 hover:text-[var(--gradient-start)] transition-colors">
                    {agent.name}
                  </h3>
                </Link>
                <p className="text-sm text-[var(--text-muted)] line-clamp-2 mb-3">
                  {agent.persona}
                </p>

                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center px-2 py-1 rounded-md text-xs font-medium bg-[var(--gradient-start)]/10 text-[var(--gradient-start)]">
                    {agent.agentModel}
                  </span>
                  <span className="inline-flex items-center px-2 py-1 rounded-md text-xs font-medium bg-white/5 text-[var(--text-muted)]">
                    {agent.llmConfig.provider}
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
              Are you sure you want to delete "{selectedAgent?.name}"? This will
              also delete all memory blocks, tools, and conversation history
              associated with this agent.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsDeleteDialogOpen(false)}
            >
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDelete}>
              Delete Agent
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
