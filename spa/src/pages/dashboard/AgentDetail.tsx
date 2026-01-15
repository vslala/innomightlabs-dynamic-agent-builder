import { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import {
  Bot,
  Brain,
  Wrench,
  ChevronLeft,
  Plus,
  Pencil,
  Trash2,
  Eye,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../../components/ui/tabs";
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
import type { Agent, MemoryBlock, MemoryBlockType, AgentTool } from "../../types/agent";

export function AgentDetail() {
  const { agentId } = useParams<{ agentId: string }>();
  const navigate = useNavigate();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [memoryBlocks, setMemoryBlocks] = useState<MemoryBlock[]>([]);
  const [tools, setTools] = useState<AgentTool[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("memory");

  // Memory block dialog
  const [isMemoryDialogOpen, setIsMemoryDialogOpen] = useState(false);
  const [editingMemoryBlock, setEditingMemoryBlock] = useState<MemoryBlock | null>(null);
  const [memoryForm, setMemoryForm] = useState({
    name: "",
    type: "read" as MemoryBlockType,
    content: "",
  });

  // Tool dialog
  const [isToolDialogOpen, setIsToolDialogOpen] = useState(false);
  const [toolForm, setToolForm] = useState({
    toolId: "",
    config: {} as Record<string, string>,
  });

  const loadData = async () => {
    if (!agentId) return;
    const service = getAgentService();
    const [agentData, memoryData, toolsData] = await Promise.all([
      service.getAgent(agentId),
      service.getMemoryBlocks(agentId),
      service.getAgentTools(agentId),
    ]);
    setAgent(agentData);
    setMemoryBlocks(memoryData);
    setTools(toolsData);
    setLoading(false);
  };

  useEffect(() => {
    loadData();
  }, [agentId]);

  const resetMemoryForm = () => {
    setMemoryForm({ name: "", type: "read", content: "" });
    setEditingMemoryBlock(null);
  };

  const handleCreateMemoryBlock = async () => {
    if (!agentId) return;
    const service = getAgentService();
    await service.createMemoryBlock({
      agentId,
      name: memoryForm.name,
      type: memoryForm.type,
      content: memoryForm.content,
    });
    setIsMemoryDialogOpen(false);
    resetMemoryForm();
    loadData();
  };

  const handleUpdateMemoryBlock = async () => {
    if (!editingMemoryBlock) return;
    const service = getAgentService();
    await service.updateMemoryBlock(editingMemoryBlock.id, {
      name: memoryForm.name,
      content: memoryForm.content,
    });
    setIsMemoryDialogOpen(false);
    resetMemoryForm();
    loadData();
  };

  const handleDeleteMemoryBlock = async (blockId: string) => {
    const service = getAgentService();
    await service.deleteMemoryBlock(blockId);
    loadData();
  };

  const openEditMemoryDialog = (block: MemoryBlock) => {
    setEditingMemoryBlock(block);
    setMemoryForm({
      name: block.name,
      type: block.type,
      content: block.content,
    });
    setIsMemoryDialogOpen(true);
  };

  const handleAddTool = async () => {
    if (!agentId) return;
    const service = getAgentService();
    await service.addToolToAgent(agentId, toolForm.toolId, toolForm.config);
    setIsToolDialogOpen(false);
    setToolForm({ toolId: "", config: {} });
    loadData();
  };

  const handleRemoveTool = async (toolId: string) => {
    const service = getAgentService();
    await service.removeToolFromAgent(toolId);
    loadData();
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--gradient-start)] border-t-transparent" />
      </div>
    );
  }

  if (!agent) {
    return (
      <div className="text-center py-12">
        <p className="text-[var(--text-muted)]">Agent not found</p>
        <Link to="/dashboard/agents">
          <Button variant="outline" className="mt-4">
            Back to Agents
          </Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" onClick={() => navigate(-1)}>
          <ChevronLeft className="h-5 w-5" />
        </Button>
        <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-[var(--gradient-start)] to-[var(--gradient-mid)] flex items-center justify-center">
          <Bot className="h-6 w-6 text-white" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-[var(--text-primary)]">
            {agent.name}
          </h1>
          <p className="text-sm text-[var(--text-muted)]">{agent.agentModel}</p>
        </div>
      </div>

      {/* Agent Info Card */}
      <Card>
        <CardContent className="p-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <Label className="text-[var(--text-muted)]">Persona</Label>
              <p className="mt-1 text-[var(--text-secondary)]">{agent.persona}</p>
            </div>
            <div>
              <Label className="text-[var(--text-muted)]">LLM Configuration</Label>
              <div className="mt-1 flex gap-2">
                <span className="inline-flex items-center px-2 py-1 rounded-md text-xs font-medium bg-white/5 text-[var(--text-secondary)]">
                  {agent.llmConfig.provider}
                </span>
                <span className="inline-flex items-center px-2 py-1 rounded-md text-xs font-medium bg-white/5 text-[var(--text-secondary)]">
                  {agent.llmConfig.model}
                </span>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="memory">
            <Brain className="h-4 w-4 mr-2" />
            Memory Blocks
          </TabsTrigger>
          <TabsTrigger value="tools">
            <Wrench className="h-4 w-4 mr-2" />
            Tools
          </TabsTrigger>
        </TabsList>

        {/* Memory Blocks Tab */}
        <TabsContent value="memory">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base">Memory Blocks</CardTitle>
              <Dialog
                open={isMemoryDialogOpen}
                onOpenChange={(open) => {
                  setIsMemoryDialogOpen(open);
                  if (!open) resetMemoryForm();
                }}
              >
                <DialogTrigger asChild>
                  <Button size="sm">
                    <Plus className="h-4 w-4 mr-2" />
                    Add Memory Block
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>
                      {editingMemoryBlock ? "Edit Memory Block" : "Add Memory Block"}
                    </DialogTitle>
                    <DialogDescription>
                      {editingMemoryBlock
                        ? "Update the memory block content"
                        : "Create a new memory block for your agent"}
                    </DialogDescription>
                  </DialogHeader>

                  <div className="space-y-4 py-4">
                    <div className="space-y-2">
                      <Label htmlFor="memoryName">Name</Label>
                      <Input
                        id="memoryName"
                        placeholder="Core personality"
                        value={memoryForm.name}
                        onChange={(e) =>
                          setMemoryForm({ ...memoryForm, name: e.target.value })
                        }
                      />
                    </div>

                    {!editingMemoryBlock && (
                      <div className="space-y-2">
                        <Label>Type</Label>
                        <Select
                          value={memoryForm.type}
                          onValueChange={(value: MemoryBlockType) =>
                            setMemoryForm({ ...memoryForm, type: value })
                          }
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="read">
                              <div className="flex items-center gap-2">
                                <Eye className="h-4 w-4" />
                                <span>Read-only</span>
                              </div>
                            </SelectItem>
                            <SelectItem value="read-write">
                              <div className="flex items-center gap-2">
                                <Pencil className="h-4 w-4" />
                                <span>Read-Write</span>
                              </div>
                            </SelectItem>
                          </SelectContent>
                        </Select>
                        <p className="text-xs text-[var(--text-muted)]">
                          {memoryForm.type === "read"
                            ? "User editable, agent can only read"
                            : "Agent can read and write to this block"}
                        </p>
                      </div>
                    )}

                    <div className="space-y-2">
                      <Label htmlFor="memoryContent">Content</Label>
                      <Textarea
                        id="memoryContent"
                        placeholder="Enter the memory content..."
                        value={memoryForm.content}
                        onChange={(e) =>
                          setMemoryForm({ ...memoryForm, content: e.target.value })
                        }
                        rows={5}
                        disabled={editingMemoryBlock?.type === "read-write"}
                      />
                      {editingMemoryBlock?.type === "read-write" && (
                        <p className="text-xs text-[var(--text-muted)]">
                          Read-write blocks are managed by the agent and cannot be edited
                        </p>
                      )}
                    </div>
                  </div>

                  <DialogFooter>
                    <Button
                      variant="outline"
                      onClick={() => setIsMemoryDialogOpen(false)}
                    >
                      Cancel
                    </Button>
                    <Button
                      onClick={
                        editingMemoryBlock
                          ? handleUpdateMemoryBlock
                          : handleCreateMemoryBlock
                      }
                      disabled={!memoryForm.name || (!editingMemoryBlock && !memoryForm.content)}
                    >
                      {editingMemoryBlock ? "Save Changes" : "Create Block"}
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            </CardHeader>
            <CardContent>
              {memoryBlocks.length === 0 ? (
                <div className="text-center py-8">
                  <Brain className="h-12 w-12 mx-auto text-[var(--text-muted)] mb-3" />
                  <p className="text-[var(--text-muted)]">No memory blocks yet</p>
                  <p className="text-sm text-[var(--text-muted)] mt-1">
                    Add memory blocks to give your agent persistent knowledge
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {memoryBlocks.map((block) => (
                    <div
                      key={block.id}
                      className="p-4 rounded-lg border border-[var(--border-subtle)] bg-white/[0.02]"
                    >
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-[var(--text-primary)]">
                            {block.name}
                          </span>
                          <span
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs ${
                              block.type === "read"
                                ? "bg-blue-500/10 text-blue-400"
                                : "bg-amber-500/10 text-amber-400"
                            }`}
                          >
                            {block.type === "read" ? (
                              <Eye className="h-3 w-3" />
                            ) : (
                              <Pencil className="h-3 w-3" />
                            )}
                            {block.type === "read" ? "Read-only" : "Read-Write"}
                          </span>
                        </div>
                        <div className="flex gap-1">
                          {block.type === "read" && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8"
                              onClick={() => openEditMemoryDialog(block)}
                            >
                              <Pencil className="h-4 w-4" />
                            </Button>
                          )}
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-red-400 hover:text-red-300"
                            onClick={() => handleDeleteMemoryBlock(block.id)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                      <p className="text-sm text-[var(--text-secondary)] whitespace-pre-wrap">
                        {block.content}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tools Tab */}
        <TabsContent value="tools">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base">Agent Tools</CardTitle>
              <Dialog open={isToolDialogOpen} onOpenChange={setIsToolDialogOpen}>
                <DialogTrigger asChild>
                  <Button size="sm">
                    <Plus className="h-4 w-4 mr-2" />
                    Add Tool
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Add Tool to Agent</DialogTitle>
                    <DialogDescription>
                      Select a tool from the store to add to this agent
                    </DialogDescription>
                  </DialogHeader>

                  <div className="space-y-4 py-4">
                    <div className="space-y-2">
                      <Label>Select Tool</Label>
                      <Select
                        value={toolForm.toolId}
                        onValueChange={(value) =>
                          setToolForm({ ...toolForm, toolId: value })
                        }
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Choose a tool..." />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="wordpress">WordPress</SelectItem>
                          <SelectItem value="gmail">Gmail</SelectItem>
                          <SelectItem value="slack">Slack</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    {toolForm.toolId && (
                      <div className="space-y-4 border-t border-[var(--border-subtle)] pt-4">
                        <p className="text-sm font-medium text-[var(--text-secondary)]">
                          Tool Configuration
                        </p>
                        {/* Dynamic config fields based on tool */}
                        {toolForm.toolId === "wordpress" && (
                          <>
                            <div className="space-y-2">
                              <Label>WordPress URL</Label>
                              <Input
                                placeholder="https://mysite.com"
                                onChange={(e) =>
                                  setToolForm({
                                    ...toolForm,
                                    config: { ...toolForm.config, url: e.target.value },
                                  })
                                }
                              />
                            </div>
                            <div className="space-y-2">
                              <Label>Username</Label>
                              <Input
                                placeholder="admin"
                                onChange={(e) =>
                                  setToolForm({
                                    ...toolForm,
                                    config: { ...toolForm.config, username: e.target.value },
                                  })
                                }
                              />
                            </div>
                            <div className="space-y-2">
                              <Label>Application Password</Label>
                              <Input
                                type="password"
                                placeholder="xxxx xxxx xxxx xxxx"
                                onChange={(e) =>
                                  setToolForm({
                                    ...toolForm,
                                    config: { ...toolForm.config, password: e.target.value },
                                  })
                                }
                              />
                            </div>
                          </>
                        )}
                        {toolForm.toolId === "gmail" && (
                          <p className="text-sm text-[var(--text-muted)]">
                            Gmail configuration will be added when tool store is ready
                          </p>
                        )}
                        {toolForm.toolId === "slack" && (
                          <p className="text-sm text-[var(--text-muted)]">
                            Slack configuration will be added when tool store is ready
                          </p>
                        )}
                      </div>
                    )}
                  </div>

                  <DialogFooter>
                    <Button
                      variant="outline"
                      onClick={() => setIsToolDialogOpen(false)}
                    >
                      Cancel
                    </Button>
                    <Button onClick={handleAddTool} disabled={!toolForm.toolId}>
                      Add Tool
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            </CardHeader>
            <CardContent>
              {tools.length === 0 ? (
                <div className="text-center py-8">
                  <Wrench className="h-12 w-12 mx-auto text-[var(--text-muted)] mb-3" />
                  <p className="text-[var(--text-muted)]">No tools configured</p>
                  <p className="text-sm text-[var(--text-muted)] mt-1">
                    Add tools to extend your agent's capabilities
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {tools.map((tool) => (
                    <div
                      key={tool.id}
                      className="p-4 rounded-lg border border-[var(--border-subtle)] bg-white/[0.02] flex items-center justify-between"
                    >
                      <div className="flex items-center gap-3">
                        <div className="h-10 w-10 rounded-lg bg-white/5 flex items-center justify-center">
                          <Wrench className="h-5 w-5 text-[var(--text-muted)]" />
                        </div>
                        <div>
                          <p className="font-medium text-[var(--text-primary)]">
                            {tool.name}
                          </p>
                          <p className="text-sm text-[var(--text-muted)]">
                            {tool.description}
                          </p>
                        </div>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-red-400 hover:text-red-300"
                        onClick={() => handleRemoveTool(tool.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
