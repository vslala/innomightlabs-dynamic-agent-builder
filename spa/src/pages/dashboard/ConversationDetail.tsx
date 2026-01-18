import { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { MessageSquare, ChevronLeft, Pencil, Trash2, Bot, Send, User, Loader2, Wrench, CheckCircle2, XCircle, Maximize2, Minimize2 } from "lucide-react";
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
import { chatService } from "../../services/chat";
import { authService } from "../../services/auth";
import { MarkdownRenderer } from "../../components/ui/markdown-renderer";
import type { ConversationResponse } from "../../types/conversation";
import { SSEEventType, type Message, type SSEEvent, type ToolActivity } from "../../types/message";

export function ConversationDetail() {
  const { conversationId } = useParams<{ conversationId: string }>();
  const navigate = useNavigate();
  const [conversation, setConversation] = useState<ConversationResponse | null>(null);
  const [agents, setAgents] = useState<AgentResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // User info for displaying profile picture
  const userInfo = authService.getUserFromToken();

  // Edit mode
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editAgentId, setEditAgentId] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Delete dialog
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  // Chat state
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);
  const [toolActivities, setToolActivities] = useState<ToolActivity[]>([]);
  const [incompleteResponse, setIncompleteResponse] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const streamingContentRef = useRef("");
  const hadToolCallsRef = useRef(false);

  // Pagination state for messages
  const [messagesCursor, setMessagesCursor] = useState<string | null>(null);
  const [hasMoreMessages, setHasMoreMessages] = useState(false);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [initialMessagesLoaded, setInitialMessagesLoaded] = useState(false);

  const loadData = async () => {
    if (!conversationId) return;
    try {
      setError(null);
      const [conversationData, agentsData, messagesData] = await Promise.all([
        conversationApiService.getConversation(conversationId),
        agentApiService.listAgents(),
        conversationApiService.getMessages(conversationId, 20),
      ]);
      setConversation(conversationData);
      setAgents(agentsData);
      // Messages come newest-first, reverse for display (oldest at top)
      setMessages(messagesData.items.reverse());
      setMessagesCursor(messagesData.next_cursor);
      setHasMoreMessages(messagesData.has_more);
      setInitialMessagesLoaded(true);
    } catch (err) {
      setError("Failed to load conversation. It may not exist or you don't have access.");
      console.error("Error loading conversation:", err);
    } finally {
      setLoading(false);
    }
  };

  // Load older messages (for infinite scroll up)
  const loadOlderMessages = async () => {
    if (!conversationId || !messagesCursor || isLoadingMessages) return;

    setIsLoadingMessages(true);
    try {
      const messagesData = await conversationApiService.getMessages(
        conversationId,
        20,
        messagesCursor
      );

      // Save scroll position to restore after prepending
      const container = messagesContainerRef.current;
      const previousScrollHeight = container?.scrollHeight || 0;

      // Prepend older messages (reverse them for display order)
      setMessages((prev) => [...messagesData.items.reverse(), ...prev]);
      setMessagesCursor(messagesData.next_cursor);
      setHasMoreMessages(messagesData.has_more);

      // Restore scroll position after DOM update
      requestAnimationFrame(() => {
        if (container) {
          const newScrollHeight = container.scrollHeight;
          container.scrollTop = newScrollHeight - previousScrollHeight;
        }
      });
    } catch (err) {
      console.error("Error loading older messages:", err);
    } finally {
      setIsLoadingMessages(false);
    }
  };

  // Handle scroll for infinite scroll up
  const handleScroll = () => {
    const container = messagesContainerRef.current;
    if (!container || isLoadingMessages || !hasMoreMessages) return;

    // Load more when scrolled near the top (within 50px)
    if (container.scrollTop < 50) {
      loadOlderMessages();
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

  // Scroll to bottom when new messages are added (not when loading older)
  const scrollToBottom = (behavior: ScrollBehavior = "smooth") => {
    messagesEndRef.current?.scrollIntoView({ behavior });
  };

  // Scroll to bottom on initial load
  useEffect(() => {
    if (initialMessagesLoaded) {
      scrollToBottom("instant");
    }
  }, [initialMessagesLoaded]);

  // Scroll to bottom when streaming content updates
  useEffect(() => {
    if (streamingContent) {
      scrollToBottom();
    }
  }, [streamingContent]);

  // Handle Escape key to exit expanded mode
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isExpanded) {
        setIsExpanded(false);
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isExpanded]);

  // Handle sending a message
  const handleSendMessage = async (messageOverride?: string) => {
    const messageToSend = messageOverride || inputValue.trim();
    if (!messageToSend || !conversation || isSending) return;

    if (!messageOverride) {
      setInputValue("");
    }
    setIsSending(true);
    setChatError(null);
    setStatusMessage(null);
    setStreamingContent("");
    setToolActivities([]);
    setIncompleteResponse(false);
    streamingContentRef.current = "";
    hadToolCallsRef.current = false;

    // Add user message to the list immediately (unless it's a retry/continue message)
    const isRetryMessage = messageOverride?.startsWith("Please continue");
    const userMsg: Message = {
      message_id: `temp-${Date.now()}`,
      conversation_id: conversation.conversation_id,
      role: "user",
      content: messageToSend,
      created_at: new Date().toISOString(),
    };
    if (!isRetryMessage) {
      setMessages((prev) => [...prev, userMsg]);
    }

    const handleEvent = (event: SSEEvent) => {
      switch (event.event_type) {
        case SSEEventType.LIFECYCLE_NOTIFICATION:
          setStatusMessage(event.content);
          break;

        case SSEEventType.AGENT_RESPONSE_TO_USER:
          setStatusMessage(null);
          streamingContentRef.current += event.content;
          setStreamingContent(streamingContentRef.current);
          break;

        case SSEEventType.MESSAGE_SAVED:
          // Update user message ID if provided
          if (event.message_id) {
            setMessages((prev) =>
              prev.map((m) =>
                m.message_id === userMsg.message_id
                  ? { ...m, message_id: event.message_id! }
                  : m
              )
            );
          }
          break;

        case SSEEventType.STREAM_COMPLETE:
          // Add assistant message to list using ref value
          if (streamingContentRef.current) {
            const assistantMsg: Message = {
              message_id: event.message_id || `assistant-${Date.now()}`,
              conversation_id: conversation.conversation_id,
              role: "assistant",
              content: streamingContentRef.current,
              created_at: new Date().toISOString(),
            };
            setMessages((msgs) => [...msgs, assistantMsg]);
          } else if (hadToolCallsRef.current) {
            // Had tool calls but no final response - incomplete
            setIncompleteResponse(true);
          }
          streamingContentRef.current = "";
          setStreamingContent("");
          setIsSending(false);
          setStatusMessage(null);
          break;

        case SSEEventType.TOOL_CALL_START:
          hadToolCallsRef.current = true;
          if (event.tool_name) {
            const activity: ToolActivity = {
              id: `tool-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
              timestamp: new Date(),
              tool_name: event.tool_name,
              status: "running",
              content: event.content,
              tool_args: event.tool_args,
            };
            setToolActivities((prev) => [...prev, activity]);
          }
          break;

        case SSEEventType.TOOL_CALL_RESULT:
          if (event.tool_name) {
            setToolActivities((prev) =>
              prev.map((activity) =>
                activity.tool_name === event.tool_name && activity.status === "running"
                  ? {
                      ...activity,
                      status: event.success ? "success" : "error",
                      content: event.content,
                    }
                  : activity
              )
            );
          }
          break;

        case SSEEventType.ERROR:
          setChatError(event.content);
          setIsSending(false);
          setStatusMessage(null);
          break;

        default:
          break;
      }
    };

    await chatService.sendMessage(
      conversation.agent_id,
      conversation.conversation_id,
      messageToSend,
      {
        onEvent: handleEvent,
        onError: (err) => {
          setChatError(err.message);
          setIsSending(false);
          setStatusMessage(null);
        },
        onComplete: () => {
          setIsSending(false);
          setStatusMessage(null);
        },
      }
    );
  };

  // Handle retry for incomplete responses
  const handleRetry = () => {
    setIncompleteResponse(false);
    handleSendMessage("Please continue your response from where you left off.");
  };

  // Handle Enter key press
  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
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

      {/* Fullscreen backdrop overlay */}
      {isExpanded && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: "#0a0a0f",
            zIndex: 49,
          }}
        />
      )}

      {/* Chat Section */}
      <Card style={{
        display: "flex",
        flexDirection: "column",
        height: isExpanded ? "100vh" : "32rem",
        ...(isExpanded ? {
          position: "fixed",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          zIndex: 50,
          maxWidth: "100%",
          borderRadius: 0,
          margin: 0,
          background: "#0d0d12",
        } : {}),
      }}>
        <CardHeader style={{
          borderBottom: "1px solid var(--border-subtle)",
          flexShrink: 0,
          display: "flex",
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "space-between",
        }}>
          <CardTitle style={{ fontSize: "1.125rem" }}>Messages</CardTitle>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setIsExpanded(!isExpanded)}
            title={isExpanded ? "Exit fullscreen" : "Expand to fullscreen"}
          >
            {isExpanded ? (
              <Minimize2 style={{ height: "1.125rem", width: "1.125rem" }} />
            ) : (
              <Maximize2 style={{ height: "1.125rem", width: "1.125rem" }} />
            )}
          </Button>
        </CardHeader>
        <CardContent style={{ flex: 1, display: "flex", flexDirection: "column", padding: 0, overflow: "hidden" }}>
          {/* Messages Area */}
          <div
            ref={messagesContainerRef}
            onScroll={handleScroll}
            style={{
              flex: 1,
              overflowY: "auto",
              padding: "1rem",
              display: "flex",
              flexDirection: "column",
              gap: "1rem",
            }}
          >
            {/* Loading indicator for older messages */}
            {isLoadingMessages && (
              <div style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                padding: "0.5rem",
                color: "var(--text-muted)",
                fontSize: "0.875rem",
              }}>
                <Loader2 style={{ height: "1rem", width: "1rem", marginRight: "0.5rem", animation: "spin 1s linear infinite" }} />
                Loading older messages...
              </div>
            )}

            {/* Load more indicator when there are more messages */}
            {hasMoreMessages && !isLoadingMessages && messages.length > 0 && (
              <div style={{
                textAlign: "center",
                padding: "0.5rem",
                color: "var(--text-muted)",
                fontSize: "0.75rem",
              }}>
                Scroll up for older messages
              </div>
            )}

            {messages.length === 0 && !streamingContent && !statusMessage ? (
              <div style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                height: "100%",
                color: "var(--text-muted)",
              }}>
                <MessageSquare style={{ height: "3rem", width: "3rem", marginBottom: "1rem", opacity: 0.5 }} />
                <p style={{ marginBottom: "0.5rem" }}>No messages yet</p>
                <p style={{ fontSize: "0.875rem" }}>Send a message to start the conversation</p>
              </div>
            ) : (
              <>
                {messages.map((msg) => (
                  <div
                    key={msg.message_id}
                    style={{
                      display: "flex",
                      gap: "0.75rem",
                      alignItems: "flex-start",
                      flexDirection: msg.role === "user" ? "row-reverse" : "row",
                    }}
                  >
                    {msg.role === "user" && userInfo?.picture ? (
                      <img
                        src={userInfo.picture}
                        alt={userInfo.name || "User"}
                        style={{
                          width: "2rem",
                          height: "2rem",
                          borderRadius: "50%",
                          flexShrink: 0,
                          objectFit: "cover",
                        }}
                      />
                    ) : (
                      <div style={{
                        width: "2rem",
                        height: "2rem",
                        borderRadius: "50%",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        flexShrink: 0,
                        backgroundColor: msg.role === "user"
                          ? "var(--gradient-start)"
                          : "rgba(102, 126, 234, 0.1)",
                      }}>
                        {msg.role === "user" ? (
                          <User style={{ height: "1rem", width: "1rem", color: "white" }} />
                        ) : (
                          <Bot style={{ height: "1rem", width: "1rem", color: "var(--gradient-start)" }} />
                        )}
                      </div>
                    )}
                    <div style={{
                      maxWidth: "70%",
                      padding: "0.75rem 1rem",
                      borderRadius: "1rem",
                      backgroundColor: msg.role === "user"
                        ? "var(--gradient-start)"
                        : "var(--bg-secondary)",
                      color: msg.role === "user" ? "white" : "var(--text-primary)",
                      wordBreak: "break-word",
                      lineHeight: "1.5",
                      ...(msg.role === "user" ? { whiteSpace: "pre-wrap" } : {}),
                    }}>
                      {msg.role === "assistant" ? (
                        <MarkdownRenderer content={msg.content} />
                      ) : (
                        msg.content
                      )}
                    </div>
                  </div>
                ))}

                {/* Streaming response */}
                {streamingContent && (
                  <div style={{ display: "flex", gap: "0.75rem", alignItems: "flex-start" }}>
                    <div style={{
                      width: "2rem",
                      height: "2rem",
                      borderRadius: "50%",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0,
                      backgroundColor: "rgba(102, 126, 234, 0.1)",
                    }}>
                      <Bot style={{ height: "1rem", width: "1rem", color: "var(--gradient-start)" }} />
                    </div>
                    <div style={{
                      maxWidth: "70%",
                      padding: "0.75rem 1rem",
                      borderRadius: "1rem",
                      backgroundColor: "var(--bg-secondary)",
                      color: "var(--text-primary)",
                      wordBreak: "break-word",
                      lineHeight: "1.5",
                    }}>
                      <MarkdownRenderer content={streamingContent} />
                      <span style={{
                        display: "inline-block",
                        width: "0.5rem",
                        height: "1rem",
                        marginLeft: "0.125rem",
                        backgroundColor: "var(--gradient-start)",
                        animation: "blink 1s infinite",
                      }} />
                    </div>
                  </div>
                )}

                {/* Tool Activities Timeline */}
                {toolActivities.length > 0 && (
                  <div style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "0.5rem",
                    padding: "0.75rem",
                    margin: "0.5rem 0",
                    borderRadius: "0.5rem",
                    backgroundColor: "var(--bg-tertiary)",
                    border: "1px solid var(--border-subtle)",
                  }}>
                    <div style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.5rem",
                      paddingBottom: "0.5rem",
                      borderBottom: "1px solid var(--border-subtle)",
                      fontSize: "0.75rem",
                      fontWeight: 600,
                      color: "var(--text-muted)",
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                    }}>
                      <Wrench style={{ height: "0.875rem", width: "0.875rem" }} />
                      Agent Activity
                    </div>
                    {toolActivities.map((activity) => (
                      <div
                        key={activity.id}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "0.5rem",
                          fontSize: "0.875rem",
                          color: "var(--text-secondary)",
                        }}
                      >
                        {activity.status === "running" ? (
                          <Loader2 style={{
                            height: "0.875rem",
                            width: "0.875rem",
                            color: "var(--gradient-start)",
                            animation: "spin 1s linear infinite",
                            flexShrink: 0,
                          }} />
                        ) : activity.status === "success" ? (
                          <CheckCircle2 style={{
                            height: "0.875rem",
                            width: "0.875rem",
                            color: "#22c55e",
                            flexShrink: 0,
                          }} />
                        ) : (
                          <XCircle style={{
                            height: "0.875rem",
                            width: "0.875rem",
                            color: "#ef4444",
                            flexShrink: 0,
                          }} />
                        )}
                        <span style={{
                          fontFamily: "monospace",
                          fontSize: "0.75rem",
                          color: "var(--text-muted)",
                          flexShrink: 0,
                        }}>
                          {activity.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                        </span>
                        <span style={{
                          fontWeight: 500,
                          color: activity.status === "running" ? "var(--gradient-start)" : "var(--text-primary)",
                        }}>
                          {activity.tool_name.replace(/_/g, " ")}
                        </span>
                        <span style={{
                          color: "var(--text-muted)",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}>
                          {activity.content}
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Status message */}
                {statusMessage && (
                  <div style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "0.5rem",
                    padding: "0.5rem",
                    color: "var(--text-muted)",
                    fontSize: "0.875rem",
                  }}>
                    <Loader2 style={{ height: "1rem", width: "1rem", animation: "spin 1s linear infinite" }} />
                    {statusMessage}
                  </div>
                )}
              </>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Error message */}
          {chatError && (
            <div style={{
              margin: "0 1rem",
              padding: "0.75rem",
              borderRadius: "0.5rem",
              backgroundColor: "rgba(239, 68, 68, 0.1)",
              border: "1px solid rgba(239, 68, 68, 0.2)",
              color: "#f87171",
              fontSize: "0.875rem",
            }}>
              {chatError}
            </div>
          )}

          {/* Incomplete response warning with retry */}
          {incompleteResponse && (
            <div style={{
              margin: "0 1rem",
              padding: "0.75rem",
              borderRadius: "0.5rem",
              backgroundColor: "rgba(245, 158, 11, 0.1)",
              border: "1px solid rgba(245, 158, 11, 0.2)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "0.75rem",
            }}>
              <span style={{ color: "#f59e0b", fontSize: "0.875rem" }}>
                The agent processed your request but didn't finish responding.
              </span>
              <Button
                size="sm"
                variant="outline"
                onClick={handleRetry}
                disabled={isSending}
                style={{ flexShrink: 0 }}
              >
                {isSending ? "Retrying..." : "Retry"}
              </Button>
            </div>
          )}

          {/* Input Area */}
          <div style={{
            display: "flex",
            gap: "0.75rem",
            padding: "1rem",
            borderTop: "1px solid var(--border-subtle)",
            alignItems: "flex-end",
          }}>
            <Textarea
              placeholder="Type your message... (Enter to send, Shift+Enter for new line)"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyPress}
              disabled={isSending}
              rows={1}
              style={{
                flex: 1,
                minHeight: "2.5rem",
                maxHeight: "10rem",
                resize: "none",
                overflow: "auto",
              }}
              onInput={(e) => {
                const target = e.target as HTMLTextAreaElement;
                target.style.height = "auto";
                target.style.height = Math.min(target.scrollHeight, 160) + "px";
              }}
            />
            <Button
              onClick={() => handleSendMessage()}
              disabled={!inputValue.trim() || isSending}
              style={{ flexShrink: 0, height: "2.5rem" }}
            >
              {isSending ? (
                <Loader2 style={{ height: "1rem", width: "1rem", animation: "spin 1s linear infinite" }} />
              ) : (
                <Send style={{ height: "1rem", width: "1rem" }} />
              )}
            </Button>
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
