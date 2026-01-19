import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Bot, ChevronLeft, Pencil, Plus, Trash2, ChevronDown, ChevronRight, Database, Lock, Key, Copy, Check, Eye, EyeOff, Globe } from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Textarea } from "../../components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";
import { SchemaForm, SchemaView } from "../../components/forms";
import {
  memoryApiService,
  type MemoryBlockResponse,
  type MemoryBlockContentResponse,
} from "../../services/memory";
import {
  apiKeyService,
  type ApiKeyResponse,
} from "../../services/apikeys";
import {
  agentApiService,
  type AgentResponse,
} from "../../services/agents/AgentApiService";
import type { FormSchema } from "../../types/form";

export function AgentDetail() {
  const { agentId } = useParams<{ agentId: string }>();
  const navigate = useNavigate();
  const [agent, setAgent] = useState<AgentResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Edit mode
  const [isEditing, setIsEditing] = useState(false);
  const [updateSchema, setUpdateSchema] = useState<FormSchema | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Memory blocks state
  const [memoryBlocks, setMemoryBlocks] = useState<MemoryBlockResponse[]>([]);
  const [expandedBlocks, setExpandedBlocks] = useState<Set<string>>(new Set());
  const [blockContents, setBlockContents] = useState<Record<string, MemoryBlockContentResponse>>({});
  const [loadingBlocks, setLoadingBlocks] = useState(false);

  // Create block dialog
  const [isCreateBlockDialogOpen, setIsCreateBlockDialogOpen] = useState(false);
  const [newBlockName, setNewBlockName] = useState("");
  const [newBlockDescription, setNewBlockDescription] = useState("");
  const [newBlockWordLimit, setNewBlockWordLimit] = useState(5000);
  const [isCreatingBlock, setIsCreatingBlock] = useState(false);
  const [createBlockError, setCreateBlockError] = useState<string | null>(null);

  // Edit content dialog
  const [editingBlock, setEditingBlock] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");
  const [isSavingContent, setIsSavingContent] = useState(false);

  // Delete block dialog
  const [deletingBlock, setDeletingBlock] = useState<string | null>(null);
  const [isDeletingBlock, setIsDeletingBlock] = useState(false);

  // API Keys state
  const [apiKeys, setApiKeys] = useState<ApiKeyResponse[]>([]);
  const [loadingApiKeys, setLoadingApiKeys] = useState(false);
  const [isCreateKeyDialogOpen, setIsCreateKeyDialogOpen] = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyOrigins, setNewKeyOrigins] = useState("");
  const [isCreatingKey, setIsCreatingKey] = useState(false);
  const [createKeyError, setCreateKeyError] = useState<string | null>(null);
  const [deletingKey, setDeletingKey] = useState<string | null>(null);
  const [isDeletingKey, setIsDeletingKey] = useState(false);
  const [copiedKeyId, setCopiedKeyId] = useState<string | null>(null);
  const [visibleKeyId, setVisibleKeyId] = useState<string | null>(null);

  const loadAgent = async () => {
    if (!agentId) return;
    try {
      setError(null);
      const data = await agentApiService.getAgent(agentId);
      setAgent(data);
    } catch (err) {
      setError("Failed to load agent. It may not exist or you don't have access.");
      console.error("Error loading agent:", err);
    } finally {
      setLoading(false);
    }
  };

  const loadUpdateSchema = async () => {
    if (!agentId) return;
    try {
      const schema = await agentApiService.getUpdateSchema(agentId);
      setUpdateSchema(schema);
    } catch (err) {
      console.error("Error loading update schema:", err);
    }
  };

  const loadMemoryBlocks = async () => {
    if (!agentId) return;
    setLoadingBlocks(true);
    try {
      const blocks = await memoryApiService.listMemoryBlocks(agentId);
      // Sort: default blocks first (human, persona), then custom blocks alphabetically
      blocks.sort((a, b) => {
        if (a.is_default && !b.is_default) return -1;
        if (!a.is_default && b.is_default) return 1;
        return a.block_name.localeCompare(b.block_name);
      });
      setMemoryBlocks(blocks);
    } catch (err) {
      console.error("Error loading memory blocks:", err);
    } finally {
      setLoadingBlocks(false);
    }
  };

  const toggleBlockExpansion = async (blockName: string) => {
    const newExpanded = new Set(expandedBlocks);
    if (expandedBlocks.has(blockName)) {
      newExpanded.delete(blockName);
    } else {
      newExpanded.add(blockName);
      // Load content if not already loaded
      if (!blockContents[blockName]) {
        try {
          const content = await memoryApiService.getMemoryBlockContent(agentId!, blockName);
          setBlockContents((prev) => ({ ...prev, [blockName]: content }));
        } catch (err) {
          console.error(`Error loading content for ${blockName}:`, err);
        }
      }
    }
    setExpandedBlocks(newExpanded);
  };

  const handleCreateBlock = async () => {
    if (!agentId || !newBlockName.trim() || !newBlockDescription.trim()) return;
    setIsCreatingBlock(true);
    setCreateBlockError(null);
    try {
      await memoryApiService.createMemoryBlock(agentId, {
        name: newBlockName.trim().toLowerCase().replace(/\s+/g, "_"),
        description: newBlockDescription.trim(),
        word_limit: newBlockWordLimit,
      });
      setIsCreateBlockDialogOpen(false);
      setNewBlockName("");
      setNewBlockDescription("");
      setNewBlockWordLimit(5000);
      loadMemoryBlocks();
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : "Failed to create memory block";
      setCreateBlockError(errorMessage);
    } finally {
      setIsCreatingBlock(false);
    }
  };

  const handleDeleteBlock = async () => {
    if (!agentId || !deletingBlock) return;
    setIsDeletingBlock(true);
    try {
      await memoryApiService.deleteMemoryBlock(agentId, deletingBlock);
      setDeletingBlock(null);
      // Remove from local state
      setMemoryBlocks((prev) => prev.filter((b) => b.block_name !== deletingBlock));
      setBlockContents((prev) => {
        const newContents = { ...prev };
        delete newContents[deletingBlock];
        return newContents;
      });
      setExpandedBlocks((prev) => {
        const newExpanded = new Set(prev);
        newExpanded.delete(deletingBlock);
        return newExpanded;
      });
    } catch (err) {
      console.error("Error deleting memory block:", err);
    } finally {
      setIsDeletingBlock(false);
    }
  };

  const handleStartEditContent = (blockName: string) => {
    const content = blockContents[blockName];
    if (content) {
      setEditContent(content.lines.join("\n"));
      setEditingBlock(blockName);
    }
  };

  const handleSaveContent = async () => {
    if (!agentId || !editingBlock) return;
    setIsSavingContent(true);
    try {
      const lines = editContent.split("\n").filter((line) => line.trim() !== "");
      const updated = await memoryApiService.updateMemoryBlockContent(agentId, editingBlock, { lines });
      setBlockContents((prev) => ({ ...prev, [editingBlock]: updated }));
      // Update the block metadata (word count, capacity)
      setMemoryBlocks((prev) =>
        prev.map((b) =>
          b.block_name === editingBlock
            ? { ...b, word_count: updated.word_count, capacity_percent: updated.capacity_percent }
            : b
        )
      );
      setEditingBlock(null);
      setEditContent("");
    } catch (err) {
      console.error("Error saving memory block content:", err);
    } finally {
      setIsSavingContent(false);
    }
  };

  // API Key handlers
  const loadApiKeys = async () => {
    if (!agentId) return;
    setLoadingApiKeys(true);
    try {
      const keys = await apiKeyService.listApiKeys(agentId);
      setApiKeys(keys);
    } catch (err) {
      console.error("Error loading API keys:", err);
    } finally {
      setLoadingApiKeys(false);
    }
  };

  const handleCreateApiKey = async () => {
    if (!agentId || !newKeyName.trim()) return;
    setIsCreatingKey(true);
    setCreateKeyError(null);
    try {
      const origins = newKeyOrigins
        .split("\n")
        .map((o) => o.trim())
        .filter((o) => o.length > 0);
      const newKey = await apiKeyService.createApiKey(agentId, {
        name: newKeyName.trim(),
        allowed_origins: origins,
      });
      setApiKeys((prev) => [newKey, ...prev]);
      setIsCreateKeyDialogOpen(false);
      setNewKeyName("");
      setNewKeyOrigins("");
      // Auto-show the new key so user can copy it
      setVisibleKeyId(newKey.key_id);
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : "Failed to create API key";
      setCreateKeyError(errorMessage);
    } finally {
      setIsCreatingKey(false);
    }
  };

  const handleDeleteApiKey = async () => {
    if (!agentId || !deletingKey) return;
    setIsDeletingKey(true);
    try {
      await apiKeyService.deleteApiKey(agentId, deletingKey);
      setApiKeys((prev) => prev.filter((k) => k.key_id !== deletingKey));
      setDeletingKey(null);
    } catch (err) {
      console.error("Error deleting API key:", err);
    } finally {
      setIsDeletingKey(false);
    }
  };

  const handleCopyKey = async (keyId: string, publicKey: string) => {
    try {
      await navigator.clipboard.writeText(publicKey);
      setCopiedKeyId(keyId);
      setTimeout(() => setCopiedKeyId(null), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  };

  const toggleKeyVisibility = (keyId: string) => {
    setVisibleKeyId((prev) => (prev === keyId ? null : keyId));
  };

  useEffect(() => {
    loadAgent();
    loadUpdateSchema();
    loadMemoryBlocks();
    loadApiKeys();
  }, [agentId]);

  const handleStartEdit = () => {
    setIsEditing(true);
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
  };

  const handleUpdate = async (data: Record<string, string>) => {
    if (!agentId) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const updated = await agentApiService.updateAgent(agentId, data);
      setAgent(updated);
      setIsEditing(false);
    } catch (err) {
      setError("Failed to update agent. Please try again.");
      console.error("Error updating agent:", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--gradient-start)] border-t-transparent" />
      </div>
    );
  }

  if (error && !agent) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate("/dashboard/agents")}
          >
            <ChevronLeft className="h-5 w-5" />
          </Button>
          <h1 className="text-xl font-semibold text-[var(--text-primary)]">
            Agent Not Found
          </h1>
        </div>
        <Card>
          <CardContent className="p-12">
            <div className="text-center">
              <Bot className="h-16 w-16 mx-auto text-[var(--text-muted)] mb-4" />
              <p className="text-[var(--text-muted)] mb-6">{error}</p>
              <Button onClick={() => navigate("/dashboard/agents")}>
                Back to Agents
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!agent) return null;

  // Dynamically build initial values from schema fields and agent data
  const initialValues: Record<string, string> = {};
  if (updateSchema) {
    for (const field of updateSchema.form_inputs) {
      // Get value from agent data, or empty string for password fields
      const fieldName = field.name;
      if (field.input_type === "password") {
        // Password fields are not returned by backend, leave empty
        initialValues[fieldName] = "";
      } else {
        // Dynamically get the value from agent object
        const value = (agent as unknown as Record<string, unknown>)[fieldName];
        initialValues[fieldName] = value != null ? String(value) : "";
      }
    }
  }

  return (
    <div style={{ maxWidth: "42rem", display: "flex", flexDirection: "column", gap: "2rem" }}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate("/dashboard/agents")}
          >
            <ChevronLeft className="h-5 w-5" />
          </Button>
          <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-[var(--gradient-start)] to-[var(--gradient-mid)] flex items-center justify-center">
            <Bot className="h-6 w-6 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-[var(--text-primary)]">
              {agent.agent_name}
            </h1>
            <p className="text-sm text-[var(--text-muted)]">
              {agent.agent_provider}
            </p>
          </div>
        </div>
        {!isEditing && (
          <Button variant="outline" onClick={handleStartEdit}>
            <Pencil className="h-4 w-4 mr-2" />
            Edit
          </Button>
        )}
      </div>

      {/* Agent Info / Edit Form */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">
            {isEditing ? "Edit Agent" : "Agent Details"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {error && (
            <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
              {error}
            </div>
          )}

          {isEditing && updateSchema ? (
            <SchemaForm
              schema={updateSchema}
              initialValues={initialValues}
              onSubmit={handleUpdate}
              onCancel={handleCancelEdit}
              submitLabel="Save Changes"
              isLoading={isSubmitting}
            />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
              {/* Agent name is always shown (not in update schema) */}
              <div>
                <Label style={{ color: "var(--text-muted)", marginBottom: "0.5rem", display: "block" }}>
                  Agent Name
                </Label>
                <p style={{ color: "var(--text-primary)", fontSize: "1rem" }}>
                  {agent.agent_name}
                </p>
              </div>

              {/* Dynamically render fields from schema */}
              {updateSchema && (
                <SchemaView
                  schema={updateSchema}
                  data={agent as unknown as Record<string, unknown>}
                />
              )}

              {/* Timestamps are metadata, always shown */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: "1rem",
                  paddingTop: "1.5rem",
                  borderTop: "1px solid var(--border-subtle)",
                }}
              >
                <div>
                  <Label style={{ color: "var(--text-muted)", marginBottom: "0.5rem", display: "block" }}>
                    Created
                  </Label>
                  <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>
                    {new Date(agent.created_at).toLocaleDateString()}
                  </p>
                </div>
                {agent.updated_at && (
                  <div>
                    <Label style={{ color: "var(--text-muted)", marginBottom: "0.5rem", display: "block" }}>
                      Last Updated
                    </Label>
                    <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>
                      {new Date(agent.updated_at).toLocaleDateString()}
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Memory Blocks Section */}
      <Card>
        <CardHeader>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <Database style={{ height: "1.25rem", width: "1.25rem", color: "var(--gradient-start)" }} />
              <CardTitle className="text-lg">Memory Blocks</CardTitle>
            </div>
            <Button size="sm" onClick={() => setIsCreateBlockDialogOpen(true)}>
              <Plus style={{ height: "1rem", width: "1rem", marginRight: "0.375rem" }} />
              New Block
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loadingBlocks ? (
            <div style={{ display: "flex", justifyContent: "center", padding: "2rem" }}>
              <div style={{
                height: "2rem",
                width: "2rem",
                animation: "spin 1s linear infinite",
                borderRadius: "50%",
                border: "2px solid var(--gradient-start)",
                borderTopColor: "transparent",
              }} />
            </div>
          ) : memoryBlocks.length === 0 ? (
            <div style={{ textAlign: "center", padding: "2rem", color: "var(--text-muted)" }}>
              <Database style={{ height: "3rem", width: "3rem", margin: "0 auto 1rem", opacity: 0.5 }} />
              <p>No memory blocks yet</p>
              <p style={{ fontSize: "0.875rem" }}>Memory blocks will be created when you start chatting with this agent</p>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {memoryBlocks.map((block) => (
                <div
                  key={block.block_name}
                  style={{
                    border: "1px solid var(--border-subtle)",
                    borderRadius: "0.5rem",
                    overflow: "hidden",
                  }}
                >
                  {/* Block header */}
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "0.75rem 1rem",
                      backgroundColor: "var(--bg-secondary)",
                      cursor: "pointer",
                    }}
                    onClick={() => toggleBlockExpansion(block.block_name)}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                      {expandedBlocks.has(block.block_name) ? (
                        <ChevronDown style={{ height: "1rem", width: "1rem", color: "var(--text-muted)" }} />
                      ) : (
                        <ChevronRight style={{ height: "1rem", width: "1rem", color: "var(--text-muted)" }} />
                      )}
                      <div>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                          <span style={{ fontWeight: 500, color: "var(--text-primary)" }}>
                            {block.block_name}
                          </span>
                          {block.is_default && (
                            <span style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "0.25rem",
                              fontSize: "0.75rem",
                              color: "var(--text-muted)",
                              backgroundColor: "var(--bg-tertiary)",
                              padding: "0.125rem 0.5rem",
                              borderRadius: "0.25rem",
                            }}>
                              <Lock style={{ height: "0.625rem", width: "0.625rem" }} />
                              default
                            </span>
                          )}
                        </div>
                        <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.125rem" }}>
                          {block.description}
                        </p>
                      </div>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                      {/* Capacity indicator */}
                      <div style={{ textAlign: "right" }}>
                        <div style={{
                          fontSize: "0.75rem",
                          color: block.capacity_percent > 80 ? "#f59e0b" : "var(--text-muted)",
                        }}>
                          {block.word_count} / {block.word_limit} words
                        </div>
                        <div style={{
                          width: "4rem",
                          height: "0.25rem",
                          backgroundColor: "var(--bg-tertiary)",
                          borderRadius: "0.125rem",
                          overflow: "hidden",
                          marginTop: "0.25rem",
                        }}>
                          <div style={{
                            width: `${Math.min(block.capacity_percent, 100)}%`,
                            height: "100%",
                            backgroundColor: block.capacity_percent > 80 ? "#f59e0b" : "var(--gradient-start)",
                            transition: "width 0.3s ease",
                          }} />
                        </div>
                      </div>
                      {/* Actions for custom blocks */}
                      {!block.is_default && (
                        <Button
                          variant="ghost"
                          size="icon"
                          style={{ color: "#f87171", height: "2rem", width: "2rem" }}
                          onClick={(e) => {
                            e.stopPropagation();
                            setDeletingBlock(block.block_name);
                          }}
                        >
                          <Trash2 style={{ height: "0.875rem", width: "0.875rem" }} />
                        </Button>
                      )}
                    </div>
                  </div>

                  {/* Expanded content */}
                  {expandedBlocks.has(block.block_name) && (
                    <div style={{ padding: "1rem", borderTop: "1px solid var(--border-subtle)" }}>
                      {blockContents[block.block_name] ? (
                        <>
                          {blockContents[block.block_name].lines.length === 0 ? (
                            <p style={{ color: "var(--text-muted)", fontStyle: "italic", fontSize: "0.875rem" }}>
                              No content yet
                            </p>
                          ) : (
                            <div style={{
                              fontFamily: "monospace",
                              fontSize: "0.8125rem",
                              backgroundColor: "var(--bg-tertiary)",
                              padding: "0.75rem",
                              borderRadius: "0.375rem",
                              maxHeight: "12rem",
                              overflowY: "auto",
                            }}>
                              {blockContents[block.block_name].lines.map((line, idx) => (
                                <div key={idx} style={{ display: "flex", gap: "0.75rem", lineHeight: "1.5" }}>
                                  <span style={{ color: "var(--text-muted)", minWidth: "1.5rem", textAlign: "right" }}>
                                    {idx + 1}:
                                  </span>
                                  <span style={{ color: "var(--text-primary)" }}>{line}</span>
                                </div>
                              ))}
                            </div>
                          )}
                          {/* Edit button for custom blocks */}
                          {!block.is_default && (
                            <div style={{ marginTop: "0.75rem", display: "flex", justifyContent: "flex-end" }}>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => handleStartEditContent(block.block_name)}
                              >
                                <Pencil style={{ height: "0.875rem", width: "0.875rem", marginRight: "0.375rem" }} />
                                Edit Content
                              </Button>
                            </div>
                          )}
                        </>
                      ) : (
                        <div style={{ display: "flex", justifyContent: "center", padding: "1rem" }}>
                          <div style={{
                            height: "1.5rem",
                            width: "1.5rem",
                            animation: "spin 1s linear infinite",
                            borderRadius: "50%",
                            border: "2px solid var(--gradient-start)",
                            borderTopColor: "transparent",
                          }} />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* API Keys Section */}
      <Card>
        <CardHeader>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <Key style={{ height: "1.25rem", width: "1.25rem", color: "var(--gradient-start)" }} />
              <CardTitle className="text-lg">Widget API Keys</CardTitle>
            </div>
            <Button size="sm" onClick={() => setIsCreateKeyDialogOpen(true)}>
              <Plus style={{ height: "1rem", width: "1rem", marginRight: "0.375rem" }} />
              New Key
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <p style={{ fontSize: "0.875rem", color: "var(--text-muted)", marginBottom: "1rem" }}>
            API keys allow you to embed this agent as a chat widget on your website.
          </p>
          {loadingApiKeys ? (
            <div style={{ display: "flex", justifyContent: "center", padding: "2rem" }}>
              <div style={{
                height: "2rem",
                width: "2rem",
                animation: "spin 1s linear infinite",
                borderRadius: "50%",
                border: "2px solid var(--gradient-start)",
                borderTopColor: "transparent",
              }} />
            </div>
          ) : apiKeys.length === 0 ? (
            <div style={{ textAlign: "center", padding: "2rem", color: "var(--text-muted)" }}>
              <Key style={{ height: "3rem", width: "3rem", margin: "0 auto 1rem", opacity: 0.5 }} />
              <p>No API keys yet</p>
              <p style={{ fontSize: "0.875rem" }}>Create an API key to embed this agent on your website</p>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {apiKeys.map((key) => (
                <div
                  key={key.key_id}
                  style={{
                    border: "1px solid var(--border-subtle)",
                    borderRadius: "0.5rem",
                    padding: "1rem",
                    backgroundColor: key.is_active ? "transparent" : "rgba(239, 68, 68, 0.05)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "1rem" }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
                        <span style={{ fontWeight: 500, color: "var(--text-primary)" }}>{key.name}</span>
                        {!key.is_active && (
                          <span style={{
                            fontSize: "0.75rem",
                            color: "#f87171",
                            backgroundColor: "rgba(239, 68, 68, 0.1)",
                            padding: "0.125rem 0.5rem",
                            borderRadius: "0.25rem",
                          }}>
                            Disabled
                          </span>
                        )}
                      </div>
                      {/* API Key value */}
                      <div style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "0.5rem",
                        fontFamily: "monospace",
                        fontSize: "0.8125rem",
                        backgroundColor: "var(--bg-tertiary)",
                        padding: "0.5rem 0.75rem",
                        borderRadius: "0.375rem",
                        marginBottom: "0.5rem",
                      }}>
                        <code style={{ color: "var(--text-secondary)", flex: 1 }}>
                          {visibleKeyId === key.key_id
                            ? key.public_key
                            : key.public_key.slice(0, 12) + "••••••••••••••••"}
                        </code>
                        <Button
                          variant="ghost"
                          size="icon"
                          style={{ height: "1.5rem", width: "1.5rem" }}
                          onClick={() => toggleKeyVisibility(key.key_id)}
                        >
                          {visibleKeyId === key.key_id ? (
                            <EyeOff style={{ height: "0.875rem", width: "0.875rem" }} />
                          ) : (
                            <Eye style={{ height: "0.875rem", width: "0.875rem" }} />
                          )}
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          style={{ height: "1.5rem", width: "1.5rem" }}
                          onClick={() => handleCopyKey(key.key_id, key.public_key)}
                        >
                          {copiedKeyId === key.key_id ? (
                            <Check style={{ height: "0.875rem", width: "0.875rem", color: "#10b981" }} />
                          ) : (
                            <Copy style={{ height: "0.875rem", width: "0.875rem" }} />
                          )}
                        </Button>
                      </div>
                      {/* Allowed origins */}
                      {key.allowed_origins.length > 0 && (
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                          <Globe style={{ height: "0.75rem", width: "0.75rem", color: "var(--text-muted)" }} />
                          {key.allowed_origins.map((origin, idx) => (
                            <span
                              key={idx}
                              style={{
                                fontSize: "0.75rem",
                                color: "var(--text-muted)",
                                backgroundColor: "var(--bg-tertiary)",
                                padding: "0.125rem 0.5rem",
                                borderRadius: "0.25rem",
                              }}
                            >
                              {origin}
                            </span>
                          ))}
                        </div>
                      )}
                      {key.allowed_origins.length === 0 && (
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                          <Globe style={{ height: "0.75rem", width: "0.75rem", color: "var(--text-muted)" }} />
                          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                            All origins allowed
                          </span>
                        </div>
                      )}
                      {/* Stats */}
                      <div style={{ display: "flex", gap: "1rem", marginTop: "0.5rem", fontSize: "0.75rem", color: "var(--text-muted)" }}>
                        <span>{key.request_count.toLocaleString()} requests</span>
                        {key.last_used_at && (
                          <span>Last used: {new Date(key.last_used_at).toLocaleDateString()}</span>
                        )}
                        <span>Created: {new Date(key.created_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      style={{ color: "#f87171", height: "2rem", width: "2rem" }}
                      onClick={() => setDeletingKey(key.key_id)}
                    >
                      <Trash2 style={{ height: "0.875rem", width: "0.875rem" }} />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
          {/* Widget integration snippet */}
          {apiKeys.length > 0 && (
            <div style={{ marginTop: "1.5rem", paddingTop: "1rem", borderTop: "1px solid var(--border-subtle)" }}>
              <p style={{ fontSize: "0.875rem", fontWeight: 500, color: "var(--text-primary)", marginBottom: "0.5rem" }}>
                Integration Code
              </p>
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
                Add this snippet to your website to embed the chat widget:
              </p>
              <div style={{
                fontFamily: "monospace",
                fontSize: "0.75rem",
                backgroundColor: "var(--bg-tertiary)",
                padding: "0.75rem",
                borderRadius: "0.375rem",
                overflowX: "auto",
              }}>
                <pre style={{ margin: 0, color: "var(--text-secondary)" }}>
{`<script src="https://cdn.innomightlabs.com/widget.js"></script>
<script>
  InnomightChat.init({
    apiKey: '${apiKeys[0]?.public_key || "YOUR_API_KEY"}',
    position: 'bottom-right'
  });
</script>`}
                </pre>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Create Block Dialog */}
      <Dialog open={isCreateBlockDialogOpen} onOpenChange={setIsCreateBlockDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Memory Block</DialogTitle>
            <DialogDescription>
              Create a new custom memory block for this agent. The agent can store and recall information in this block.
            </DialogDescription>
          </DialogHeader>
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            {createBlockError && (
              <div style={{
                padding: "0.75rem",
                borderRadius: "0.5rem",
                backgroundColor: "rgba(239, 68, 68, 0.1)",
                border: "1px solid rgba(239, 68, 68, 0.2)",
                color: "#f87171",
                fontSize: "0.875rem",
              }}>
                {createBlockError}
              </div>
            )}
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <Label htmlFor="block-name">Block Name *</Label>
              <Input
                id="block-name"
                placeholder="e.g., projects, goals, preferences"
                value={newBlockName}
                onChange={(e) => setNewBlockName(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""))}
              />
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                Lowercase letters, numbers, and underscores only
              </p>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <Label htmlFor="block-description">Description *</Label>
              <Input
                id="block-description"
                placeholder="What information will be stored in this block?"
                value={newBlockDescription}
                onChange={(e) => setNewBlockDescription(e.target.value)}
              />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <Label htmlFor="block-limit">Word Limit</Label>
              <Input
                id="block-limit"
                type="number"
                min={100}
                max={50000}
                value={newBlockWordLimit}
                onChange={(e) => setNewBlockWordLimit(parseInt(e.target.value) || 5000)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsCreateBlockDialogOpen(false)} disabled={isCreatingBlock}>
              Cancel
            </Button>
            <Button
              onClick={handleCreateBlock}
              disabled={!newBlockName.trim() || !newBlockDescription.trim() || isCreatingBlock}
            >
              {isCreatingBlock ? "Creating..." : "Create Block"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Block Dialog */}
      <Dialog open={!!deletingBlock} onOpenChange={() => setDeletingBlock(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Memory Block</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete the "{deletingBlock}" memory block?
              This will permanently delete all content stored in this block.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeletingBlock(null)} disabled={isDeletingBlock}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDeleteBlock} disabled={isDeletingBlock}>
              {isDeletingBlock ? "Deleting..." : "Delete Block"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Content Dialog */}
      <Dialog open={!!editingBlock} onOpenChange={() => setEditingBlock(null)}>
        <DialogContent style={{ maxWidth: "36rem" }}>
          <DialogHeader>
            <DialogTitle>Edit Memory Block Content</DialogTitle>
            <DialogDescription>
              Edit the content of the "{editingBlock}" memory block. Each line represents one piece of information.
            </DialogDescription>
          </DialogHeader>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <Label htmlFor="edit-content">Content (one item per line)</Label>
            <Textarea
              id="edit-content"
              rows={10}
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              style={{ fontFamily: "monospace", fontSize: "0.875rem" }}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditingBlock(null)} disabled={isSavingContent}>
              Cancel
            </Button>
            <Button onClick={handleSaveContent} disabled={isSavingContent}>
              {isSavingContent ? "Saving..." : "Save Changes"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create API Key Dialog */}
      <Dialog open={isCreateKeyDialogOpen} onOpenChange={setIsCreateKeyDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create API Key</DialogTitle>
            <DialogDescription>
              Create a new API key to embed this agent as a chat widget on your website.
            </DialogDescription>
          </DialogHeader>
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            {createKeyError && (
              <div style={{
                padding: "0.75rem",
                borderRadius: "0.5rem",
                backgroundColor: "rgba(239, 68, 68, 0.1)",
                border: "1px solid rgba(239, 68, 68, 0.2)",
                color: "#f87171",
                fontSize: "0.875rem",
              }}>
                {createKeyError}
              </div>
            )}
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <Label htmlFor="key-name">Key Name *</Label>
              <Input
                id="key-name"
                placeholder="e.g., Production Website, Development"
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
              />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <Label htmlFor="key-origins">Allowed Origins (optional)</Label>
              <Textarea
                id="key-origins"
                placeholder="https://example.com&#10;https://www.example.com"
                value={newKeyOrigins}
                onChange={(e) => setNewKeyOrigins(e.target.value)}
                rows={3}
              />
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                One URL per line. Leave empty to allow all origins (not recommended for production).
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsCreateKeyDialogOpen(false)} disabled={isCreatingKey}>
              Cancel
            </Button>
            <Button
              onClick={handleCreateApiKey}
              disabled={!newKeyName.trim() || isCreatingKey}
            >
              {isCreatingKey ? "Creating..." : "Create Key"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete API Key Dialog */}
      <Dialog open={!!deletingKey} onOpenChange={() => setDeletingKey(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete API Key</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete this API key? Any websites using this key will no longer be able to access the widget.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeletingKey(null)} disabled={isDeletingKey}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDeleteApiKey} disabled={isDeletingKey}>
              {isDeletingKey ? "Deleting..." : "Delete Key"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
