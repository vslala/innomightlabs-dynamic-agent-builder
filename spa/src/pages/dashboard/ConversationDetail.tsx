import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { MessageSquare, ChevronLeft, Pencil, Trash2, Bot } from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../components/ui/card";
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

export function ConversationDetail() {
  const { conversationId } = useParams<{ conversationId: string }>();
  const navigate = useNavigate();
  const [conversation, setConversation] = useState<ConversationResponse | null>(null);
  const [agents, setAgents] = useState<AgentResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Edit mode
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editAgentId, setEditAgentId] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Delete dialog
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const loadData = async () => {
    if (!conversationId) return;
    try {
      setError(null);
      const [conversationData, agentsData] = await Promise.all([
        conversationApiService.getConversation(conversationId),
        agentApiService.listAgents(),
      ]);
      setConversation(conversationData);
      setAgents(agentsData);
    } catch (err) {
      setError("Failed to load conversation. It may not exist or you don't have access.");
      console.error("Error loading conversation:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [conversationId]);

  const getAgentName = (agentId: string): string => {
    const agent = agents.find((a) => a.agent_id === agentId);
    return agent?.agent_name || "Unknown Agent";
  };

  const formatDate = (dateString: string): string => {
    return new Date(dateString).toLocaleDateString(undefined, {
      year: "numeric",
      month: "long",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const handleStartEdit = () => {
    if (!conversation) return;
    setEditTitle(conversation.title);
    setEditDescription(conversation.description || "");
    setEditAgentId(conversation.agent_id);
    setIsEditing(true);
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    setError(null);
  };

  const handleUpdate = async () => {
    if (!conversationId || !editTitle.trim() || !editAgentId) return;

    setIsSubmitting(true);
    setError(null);

    try {
      const updated = await conversationApiService.updateConversation(conversationId, {
        title: editTitle.trim(),
        description: editDescription.trim() || undefined,
        agent_id: editAgentId,
      });
      setConversation(updated);
      setIsEditing(false);
    } catch (err) {
      setError("Failed to update conversation. Please try again.");
      console.error("Error updating conversation:", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!conversationId) return;

    setIsDeleting(true);
    try {
      await conversationApiService.deleteConversation(conversationId);
      navigate("/dashboard/conversations");
    } catch (err) {
      console.error("Error deleting conversation:", err);
      setIsDeleting(false);
    }
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

  if (error && !conversation) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate("/dashboard/conversations")}
          >
            <ChevronLeft style={{ height: "1.25rem", width: "1.25rem" }} />
          </Button>
          <h1 style={{ fontSize: "1.25rem", fontWeight: 600, color: "var(--text-primary)" }}>
            Conversation Not Found
          </h1>
        </div>
        <Card>
          <CardContent style={{ padding: "3rem" }}>
            <div style={{ textAlign: "center" }}>
              <MessageSquare style={{ height: "4rem", width: "4rem", margin: "0 auto", color: "var(--text-muted)", marginBottom: "1rem" }} />
              <p style={{ color: "var(--text-muted)", marginBottom: "1.5rem" }}>{error}</p>
              <Button onClick={() => navigate("/dashboard/conversations")}>
                Back to Conversations
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!conversation) return null;

  return (
    <div style={{ maxWidth: "42rem", display: "flex", flexDirection: "column", gap: "2rem" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate("/dashboard/conversations")}
          >
            <ChevronLeft style={{ height: "1.25rem", width: "1.25rem" }} />
          </Button>
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
          <div>
            <h1 style={{ fontSize: "1.25rem", fontWeight: 600, color: "var(--text-primary)" }}>
              {conversation.title}
            </h1>
            <p style={{ fontSize: "0.875rem", color: "var(--text-muted)" }}>
              {getAgentName(conversation.agent_id)}
            </p>
          </div>
        </div>
        {!isEditing && (
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <Button variant="outline" onClick={handleStartEdit}>
              <Pencil style={{ height: "1rem", width: "1rem", marginRight: "0.5rem" }} />
              Edit
            </Button>
            <Button
              variant="ghost"
              size="icon"
              style={{ color: "#f87171" }}
              onClick={() => setIsDeleteDialogOpen(true)}
            >
              <Trash2 style={{ height: "1rem", width: "1rem" }} />
            </Button>
          </div>
        )}
      </div>

      {/* Conversation Details */}
      <Card>
        <CardHeader>
          <CardTitle style={{ fontSize: "1.125rem" }}>
            {isEditing ? "Edit Conversation" : "Conversation Details"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {error && (
            <div style={{
              marginBottom: "1rem",
              padding: "0.75rem",
              borderRadius: "0.5rem",
              backgroundColor: "rgba(239, 68, 68, 0.1)",
              border: "1px solid rgba(239, 68, 68, 0.2)",
              color: "#f87171",
              fontSize: "0.875rem",
            }}>
              {error}
            </div>
          )}

          {isEditing ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                <Label htmlFor="title">Title *</Label>
                <Input
                  id="title"
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                />
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                <Label htmlFor="description">Description</Label>
                <Textarea
                  id="description"
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  rows={4}
                />
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                <Label htmlFor="agent">Agent *</Label>
                <Select value={editAgentId} onValueChange={setEditAgentId}>
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

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem", paddingTop: "0.5rem" }}>
                <Button variant="outline" onClick={handleCancelEdit} disabled={isSubmitting}>
                  Cancel
                </Button>
                <Button
                  onClick={handleUpdate}
                  disabled={!editTitle.trim() || !editAgentId || isSubmitting}
                >
                  {isSubmitting ? "Saving..." : "Save Changes"}
                </Button>
              </div>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
              <div>
                <Label style={{ color: "var(--text-muted)", marginBottom: "0.5rem", display: "block" }}>
                  Title
                </Label>
                <p style={{ color: "var(--text-primary)", fontSize: "1rem" }}>
                  {conversation.title}
                </p>
              </div>

              <div>
                <Label style={{ color: "var(--text-muted)", marginBottom: "0.5rem", display: "block" }}>
                  Description
                </Label>
                <p style={{ color: "var(--text-secondary)", whiteSpace: "pre-wrap", lineHeight: "1.6" }}>
                  {conversation.description || "No description provided"}
                </p>
              </div>

              <div>
                <Label style={{ color: "var(--text-muted)", marginBottom: "0.5rem", display: "block" }}>
                  Agent
                </Label>
                <span style={{
                  display: "inline-flex",
                  alignItems: "center",
                  padding: "0.375rem 0.75rem",
                  borderRadius: "0.375rem",
                  fontSize: "0.875rem",
                  fontWeight: 500,
                  backgroundColor: "rgba(102, 126, 234, 0.1)",
                  color: "var(--gradient-start)",
                }}>
                  <Bot style={{ height: "0.875rem", width: "0.875rem", marginRight: "0.375rem" }} />
                  {getAgentName(conversation.agent_id)}
                </span>
              </div>

              <div style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "1rem",
                paddingTop: "1.5rem",
                borderTop: "1px solid var(--border-subtle)",
              }}>
                <div>
                  <Label style={{ color: "var(--text-muted)", marginBottom: "0.5rem", display: "block" }}>
                    Created
                  </Label>
                  <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>
                    {formatDate(conversation.created_at)}
                  </p>
                </div>
                {conversation.updated_at && (
                  <div>
                    <Label style={{ color: "var(--text-muted)", marginBottom: "0.5rem", display: "block" }}>
                      Last Updated
                    </Label>
                    <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>
                      {formatDate(conversation.updated_at)}
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Chat Placeholder */}
      <Card>
        <CardHeader>
          <CardTitle style={{ fontSize: "1.125rem" }}>Messages</CardTitle>
        </CardHeader>
        <CardContent>
          <div style={{
            textAlign: "center",
            padding: "3rem 1rem",
            color: "var(--text-muted)",
          }}>
            <MessageSquare style={{ height: "3rem", width: "3rem", margin: "0 auto", marginBottom: "1rem", opacity: 0.5 }} />
            <p style={{ marginBottom: "0.5rem" }}>Chat functionality coming soon</p>
            <p style={{ fontSize: "0.875rem" }}>
              You'll be able to interact with your agent here
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Delete Confirmation Dialog */}
      <Dialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Conversation</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete "{conversation.title}"?
              This action cannot be undone and all messages will be lost.
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
