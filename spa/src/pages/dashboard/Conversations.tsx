import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { MessageSquare, Plus, Trash2, Bot } from "lucide-react";
import { Card, CardContent } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";
import { Label } from "../../components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../components/ui/select";
import { conversationApiService } from "../../services/conversations";
import { agentApiService, type AgentResponse } from "../../services/agents/AgentApiService";
import type { ConversationResponse } from "../../types/conversation";

export function Conversations() {
  const navigate = useNavigate();
  const [conversations, setConversations] = useState<ConversationResponse[]>([]);
  const [agents, setAgents] = useState<AgentResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Create dialog state
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [selectedAgentId, setSelectedAgentId] = useState<string>("");
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Delete dialog state
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [selectedConversation, setSelectedConversation] = useState<ConversationResponse | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const loadData = async () => {
    try {
      setError(null);
      const [conversationsData, agentsData] = await Promise.all([
        conversationApiService.listConversations(),
        agentApiService.listAgents(),
      ]);
      setConversations(conversationsData.items);
      setAgents(agentsData);
    } catch (err) {
      setError("Failed to load data. Please try again.");
      console.error("Error loading data:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const getAgentName = (agentId: string): string => {
    const agent = agents.find((a) => a.agent_id === agentId);
    return agent?.agent_name || "Unknown Agent";
  };

  const formatDate = (dateString: string): string => {
    return new Date(dateString).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  };

  const handleCreate = async () => {
    if (!newTitle.trim() || !selectedAgentId) return;

    setIsCreating(true);
    setCreateError(null);

    try {
      await conversationApiService.createConversation({
        title: newTitle.trim(),
        description: newDescription.trim() || undefined,
        agent_id: selectedAgentId,
      });
      setIsCreateDialogOpen(false);
      setNewTitle("");
      setNewDescription("");
      setSelectedAgentId("");
      loadData();
    } catch (err) {
      setCreateError("Failed to create conversation. Please try again.");
      console.error("Error creating conversation:", err);
    } finally {
      setIsCreating(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedConversation) return;

    setIsDeleting(true);
    try {
      await conversationApiService.deleteConversation(selectedConversation.conversation_id);
      setIsDeleteDialogOpen(false);
      setSelectedConversation(null);
      loadData();
    } catch (err) {
      console.error("Error deleting conversation:", err);
    } finally {
      setIsDeleting(false);
    }
  };

  const openCreateDialog = () => {
    setNewTitle("");
    setNewDescription("");
    setSelectedAgentId("");
    setCreateError(null);
    setIsCreateDialogOpen(true);
  };

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "16rem" }}>
        <div style={{
          height: "2rem",
          width: "2rem",
          animation: "spin 1s linear infinite",
          borderRadius: "50%",
          border: "2px solid var(--gradient-start)",
          borderTopColor: "transparent",
        }} />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "16rem", gap: "1rem" }}>
        <p style={{ color: "#f87171" }}>{error}</p>
        <Button onClick={loadData}>Try Again</Button>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "2rem" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <p style={{ color: "var(--text-secondary)", fontSize: "1rem" }}>
            Manage your conversations with AI agents
          </p>
        </div>
        <Button onClick={openCreateDialog} size="lg" disabled={agents.length === 0}>
          <Plus style={{ height: "1.25rem", width: "1.25rem", marginRight: "0.5rem" }} />
          New Conversation
        </Button>
      </div>

      {/* No Agents Warning */}
      {agents.length === 0 && (
        <Card>
          <CardContent style={{ padding: "3rem" }}>
            <div style={{ textAlign: "center" }}>
              <Bot style={{ height: "4rem", width: "4rem", margin: "0 auto", color: "var(--text-muted)", marginBottom: "1rem" }} />
              <h3 style={{ fontSize: "1.125rem", fontWeight: 500, color: "var(--text-primary)", marginBottom: "0.5rem" }}>
                Create an agent first
              </h3>
              <p style={{ color: "var(--text-muted)", marginBottom: "1.5rem", maxWidth: "20rem", margin: "0 auto 1.5rem" }}>
                You need at least one agent to start a conversation.
              </p>
              <Button onClick={() => navigate("/dashboard/agents/new")}>
                <Plus style={{ height: "1rem", width: "1rem", marginRight: "0.5rem" }} />
                Create Agent
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Conversations Grid */}
      {agents.length > 0 && conversations.length === 0 ? (
        <Card>
          <CardContent style={{ padding: "3rem" }}>
            <div style={{ textAlign: "center" }}>
              <MessageSquare style={{ height: "4rem", width: "4rem", margin: "0 auto", color: "var(--text-muted)", marginBottom: "1rem" }} />
              <h3 style={{ fontSize: "1.125rem", fontWeight: 500, color: "var(--text-primary)", marginBottom: "0.5rem" }}>
                No conversations yet
              </h3>
              <p style={{ color: "var(--text-muted)", marginBottom: "1.5rem", maxWidth: "24rem", margin: "0 auto 1.5rem" }}>
                Start your first conversation with an AI agent. Each conversation can have its own context and history.
              </p>
              <Button onClick={openCreateDialog}>
                <Plus style={{ height: "1rem", width: "1rem", marginRight: "0.5rem" }} />
                Start Your First Conversation
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(20rem, 1fr))", gap: "1.5rem" }}>
          {conversations.map((conversation) => (
            <Card
              key={conversation.conversation_id}
              style={{ transition: "all 0.2s", cursor: "pointer" }}
              className="group hover:border-[var(--gradient-start)]/50"
            >
              <CardContent style={{ padding: "1.5rem" }}>
                <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "1rem" }}>
                  <div style={{
                    height: "3rem",
                    width: "3rem",
                    borderRadius: "0.75rem",
                    background: "linear-gradient(to bottom right, var(--gradient-start), var(--gradient-mid))",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}>
                    <MessageSquare style={{ height: "1.5rem", width: "1.5rem", color: "white" }} />
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    style={{ height: "2rem", width: "2rem" }}
                    className="text-red-400 hover:text-red-500 hover:bg-red-500/10"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedConversation(conversation);
                      setIsDeleteDialogOpen(true);
                    }}
                  >
                    <Trash2 style={{ height: "1rem", width: "1rem" }} />
                  </Button>
                </div>

                <Link to={`/dashboard/conversations/${conversation.conversation_id}`}>
                  <h3 style={{
                    fontWeight: 600,
                    fontSize: "1.125rem",
                    color: "var(--text-primary)",
                    marginBottom: "0.5rem",
                    transition: "color 0.2s",
                  }}
                  className="hover:text-[var(--gradient-start)]"
                  >
                    {conversation.title}
                  </h3>
                </Link>

                {conversation.description && (
                  <p style={{
                    fontSize: "0.875rem",
                    color: "var(--text-muted)",
                    marginBottom: "1rem",
                    lineHeight: "1.5",
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical",
                    overflow: "hidden",
                  }}>
                    {conversation.description}
                  </p>
                )}

                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem" }}>
                  <span style={{
                    display: "inline-flex",
                    alignItems: "center",
                    padding: "0.375rem 0.75rem",
                    borderRadius: "0.375rem",
                    fontSize: "0.75rem",
                    fontWeight: 500,
                    backgroundColor: "rgba(102, 126, 234, 0.1)",
                    color: "var(--gradient-start)",
                  }}>
                    <Bot style={{ height: "0.75rem", width: "0.75rem", marginRight: "0.375rem" }} />
                    {getAgentName(conversation.agent_id)}
                  </span>
                </div>

                <div style={{
                  display: "flex",
                  justifyContent: "space-between",
                  fontSize: "0.75rem",
                  color: "var(--text-muted)",
                  paddingTop: "0.75rem",
                  borderTop: "1px solid var(--border-subtle)",
                }}>
                  <span>Created: {formatDate(conversation.created_at)}</span>
                  {conversation.updated_at && (
                    <span>Updated: {formatDate(conversation.updated_at)}</span>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create Conversation Dialog */}
      <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New Conversation</DialogTitle>
            <DialogDescription>
              Start a new conversation with an AI agent.
            </DialogDescription>
          </DialogHeader>

          <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
            {createError && (
              <div style={{
                padding: "0.75rem",
                borderRadius: "0.5rem",
                backgroundColor: "rgba(239, 68, 68, 0.1)",
                border: "1px solid rgba(239, 68, 68, 0.2)",
                color: "#f87171",
                fontSize: "0.875rem",
              }}>
                {createError}
              </div>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <Label htmlFor="title">Title *</Label>
              <Input
                id="title"
                placeholder="Enter conversation title"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
              />
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <Label htmlFor="description">Description</Label>
              <Textarea
                id="description"
                placeholder="Optional description for this conversation"
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
                rows={3}
              />
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <Label htmlFor="agent">Agent *</Label>
              <Select value={selectedAgentId} onValueChange={setSelectedAgentId}>
                <SelectTrigger>
                  <SelectValue placeholder="Select an agent" />
                </SelectTrigger>
                <SelectContent>
                  {agents.map((agent) => (
                    <SelectItem key={agent.agent_id} value={agent.agent_id}>
                      {agent.agent_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsCreateDialogOpen(false)}
              disabled={isCreating}
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreate}
              disabled={!newTitle.trim() || !selectedAgentId || isCreating}
            >
              {isCreating ? "Creating..." : "Create Conversation"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Conversation</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete "{selectedConversation?.title}"?
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
              {isDeleting ? "Deleting..." : "Delete Conversation"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
