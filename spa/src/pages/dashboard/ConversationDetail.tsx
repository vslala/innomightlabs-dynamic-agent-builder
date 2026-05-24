import { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { MessageSquare, ChevronLeft, Pencil, Trash2, Bot, Send, Loader2, Maximize2, Minimize2, Paperclip, Image as ImageIcon } from "lucide-react";
import { ChatFormRenderer, type FormAnswer } from "../../components/chat/ChatFormRenderer";
import { AttachmentChip } from "../../components/chat/AttachmentChip";
import { ChatStreamRenderer } from "../../components/chat/ChatStreamRenderer";
import { useFileAttachments } from "../../hooks/useFileAttachments";
import { ALLOWED_EXTENSIONS } from "../../types/message";
import {
  Card,
  CardContent,
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
import type { ConversationResponse } from "../../types/conversation";
import type { FormSchema } from "../../types/form";
import { SSEEventType, type Message, type SSEEvent, type ToolActivity } from "../../types/message";
import styles from "./Conversation.module.css";

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
  const [activeForm, setActiveForm] = useState<{ form: FormSchema; submitLabel?: string } | null>(null);
  const [pendingFormLabel, setPendingFormLabel] = useState<string | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);
  const [toolActivities, setToolActivities] = useState<ToolActivity[]>([]);
  const [incompleteResponse, setIncompleteResponse] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isImageDialogOpen, setIsImageDialogOpen] = useState(false);
  const [imagePrompt, setImagePrompt] = useState("");
  const [isGeneratingImage, setIsGeneratingImage] = useState(false);
  const [streamingImagePreview, setStreamingImagePreview] = useState<{
    prompt: string;
    dataUrl: string | null;
    status: string;
  } | null>(null);
  const [imagePasteWarningOpen, setImagePasteWarningOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const streamingContentRef = useRef("");
  const hadToolCallsRef = useRef(false);
  const renderedFormRef = useRef(false);
  const assistantMessageSavedRef = useRef(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const {
    attachments,
    error: attachmentError,
    addFiles,
    removeAttachment,
    clearAttachments,
  } = useFileAttachments();

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

  const currentAgent = conversation
    ? agents.find((agent) => agent.agent_id === conversation.agent_id)
    : null;
  const supportsImageGeneration = currentAgent?.capabilities?.includes("image_generation") ?? false;
  const supportsImageUnderstanding = currentAgent?.capabilities?.includes("image_understanding") ?? false;

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
  const handleSendMessage = async (messageOverride?: string, optimisticUserContent?: string) => {
    const messageToSend = messageOverride || inputValue.trim();
    // Allow sending if there's a message OR attachments
    if ((!messageToSend && attachments.length === 0) || !conversation || isSending) return;

    // Capture attachments before clearing
    const attachmentsToSend = attachments.length > 0 ? [...attachments] : undefined;

    if (!messageOverride) {
      setInputValue("");
      clearAttachments();
    }
    setIsSending(true);
    setChatError(null);
    setStatusMessage(null);
    setStreamingContent("");
    setToolActivities([]);
    setActiveForm(null);
    setIncompleteResponse(false);
    streamingContentRef.current = "";
    hadToolCallsRef.current = false;
    renderedFormRef.current = false;
    assistantMessageSavedRef.current = false;

    // Add user message to the list immediately (unless it's a retry/continue message)
    const isRetryMessage = messageOverride?.startsWith("Please continue");
    const userMsg: Message = {
      message_id: `temp-${Date.now()}`,
      conversation_id: conversation.conversation_id,
      role: "user",
      content: optimisticUserContent ?? (messageToSend || "(attachments only)"),
      attachments: attachmentsToSend?.map((a) => ({ filename: a.filename, size: a.size })),
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

        case SSEEventType.UI_FORM_RENDER:
          if (event.form) {
            renderedFormRef.current = true;
            setPendingFormLabel(null);
            setActiveForm({
              form: event.form,
              submitLabel: event.submit_label || undefined,
            });
          }
          break;

        case SSEEventType.USER_MESSAGE_SAVED:
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

        case SSEEventType.ASSISTANT_MESSAGE_SAVED:
          // Add assistant message to list using ref value
          if (streamingContentRef.current) {
            assistantMessageSavedRef.current = true;
            const assistantMsg: Message = {
              message_id: event.message_id || `assistant-${Date.now()}`,
              conversation_id: conversation.conversation_id,
              role: "assistant",
              content: streamingContentRef.current,
              created_at: new Date().toISOString(),
            };
            setMessages((msgs) => [...msgs, assistantMsg]);
          }
          break;

        case SSEEventType.STREAM_COMPLETE:
          if (
            !assistantMessageSavedRef.current &&
            hadToolCallsRef.current &&
            !renderedFormRef.current
          ) {
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
      messageToSend || "",
      attachmentsToSend,
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

  const handleFormSubmit = async (answers: FormAnswer[]) => {
    if (!activeForm) return;

    const label = activeForm.form.form_name;
    setPendingFormLabel(label);

    const lines: string[] = [];
    lines.push(`<form_submission label="${label}">`);

    for (const answer of answers) {
      const displayValue = answer.value.replace(/\n/g, "\\n");
      lines.push(`- ${answer.label}: ${displayValue}`);
    }

    lines.push(`</form_submission>`);
    lines.push("");
    lines.push("Fields:");

    for (const answer of answers) {
      const value = answer.value.replace(/\n/g, " ");
      lines.push(`- ${answer.field_id}="${value}"`);
    }

    await handleSendMessage(lines.join("\n"), `Submitted: ${label}`);
  };

  const handleGenerateImage = async () => {
    if (!conversation || !imagePrompt.trim() || isGeneratingImage) return;

    const prompt = imagePrompt.trim();
    setIsGeneratingImage(true);
    setChatError(null);
    setStatusMessage(null);
    setStreamingImagePreview({
      prompt,
      dataUrl: null,
      status: "Starting image generation...",
    });
    setImagePrompt("");
    setIsImageDialogOpen(false);

    let userMessageId: string | null = null;
    let assistantMessageId: string | null = null;

    try {
      await chatService.generateImageStream(
        conversation.agent_id,
        conversation.conversation_id,
        {
          prompt,
          output_format: "png",
        },
        {
          onEvent: (event) => {
            switch (event.event_type) {
              case SSEEventType.USER_MESSAGE_SAVED:
                userMessageId = event.message_id || null;
                setMessages((prev) => [
                  ...prev,
                  {
                    message_id: userMessageId || `image-user-${Date.now()}`,
                    conversation_id: conversation.conversation_id,
                    role: "user",
                    content: prompt,
                    created_at: new Date().toISOString(),
                  },
                ]);
                break;

              case SSEEventType.IMAGE_GENERATION_STARTED:
              case SSEEventType.LIFECYCLE_NOTIFICATION:
                setStreamingImagePreview((prev) =>
                  prev ? { ...prev, status: event.content } : prev
                );
                break;

              case SSEEventType.IMAGE_GENERATION_PARTIAL:
                if (event.image_b64) {
                  setStreamingImagePreview({
                    prompt,
                    dataUrl: `data:${event.image_mime_type || "image/png"};base64,${event.image_b64}`,
                    status: "Painting preview...",
                  });
                }
                break;

              case SSEEventType.ASSISTANT_MESSAGE_SAVED:
                assistantMessageId = event.message_id || null;
                break;

              case SSEEventType.IMAGE_GENERATION_COMPLETE:
                if (event.images && event.images.length > 0) {
                  const completedImages = event.images;
                  setMessages((prev) => [
                    ...prev,
                    {
                      message_id: assistantMessageId || event.message_id || `assistant-image-${Date.now()}`,
                      conversation_id: conversation.conversation_id,
                      role: "assistant",
                      content: `Generated image: ${prompt}`,
                      images: completedImages.map((image) => ({
                        image_id: image.image_id,
                        url: image.url,
                        filename: image.filename,
                        mime_type: image.mime_type,
                        size_bytes: image.size_bytes,
                        width: image.width,
                        height: image.height,
                        prompt: image.prompt,
                        revised_prompt: image.revised_prompt,
                      })),
                      created_at: new Date().toISOString(),
                    },
                  ]);
                }
                setStreamingImagePreview(null);
                break;

              case SSEEventType.ERROR:
                setChatError(event.content);
                setStreamingImagePreview(null);
                setIsGeneratingImage(false);
                break;

              case SSEEventType.STREAM_COMPLETE:
                setStreamingImagePreview(null);
                setIsGeneratingImage(false);
                requestAnimationFrame(() => scrollToBottom());
                break;

              default:
                break;
            }
          },
          onError: (err) => {
            setChatError(err.message);
            setStreamingImagePreview(null);
            setIsGeneratingImage(false);
          },
          onComplete: () => {
            setIsGeneratingImage(false);
          },
        }
      );
    } catch (err) {
      setChatError(err instanceof Error ? err.message : String(err));
      setStreamingImagePreview(null);
      setIsGeneratingImage(false);
    } finally {
      setStatusMessage(null);
    }
  };

  const handleChatPaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const hasImage = Array.from(e.clipboardData.items).some((item) =>
      item.type.startsWith("image/")
    );
    if (hasImage && !supportsImageUnderstanding) {
      e.preventDefault();
      setImagePasteWarningOpen(true);
    }
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
      <div className={styles.loadingPanel}>
        <div className={styles.loadingSpinner} />
      </div>
    );
  }

  if (error && !conversation) {
    return (
      <div className={styles.notFoundShell}>
        <div className={styles.notFoundHeader}>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate("/dashboard/conversations")}
          >
            <ChevronLeft style={{ height: "1.25rem", width: "1.25rem" }} />
          </Button>
          <h1 className={styles.notFoundTitle}>
            Conversation Not Found
          </h1>
        </div>
        <Card>
          <CardContent className={styles.notFoundCardContent}>
            <div className={styles.notFoundBody}>
              <MessageSquare className={styles.notFoundIcon} />
              <p className={styles.notFoundMessage}>{error}</p>
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
    <div className={styles.shell}>
      <div className={styles.header}>
        <div className={styles.headerMain}>
          <Button variant="ghost" size="icon" onClick={() => navigate("/dashboard/conversations")}>
            <ChevronLeft style={{ height: "1.25rem", width: "1.25rem" }} />
          </Button>
          <div className={styles.conversationIcon}>
            <MessageSquare className={styles.conversationIconSvg} />
          </div>
          <div className={styles.headerText}>
            <div className={styles.titleRow}>
              <h1 className={styles.title}>
                {conversation.title}
              </h1>
              {supportsImageGeneration && (
                <span className={styles.imageBadge}>
                  <ImageIcon className={styles.badgeIcon} />
                  Images
                </span>
              )}
            </div>
            <div className={styles.metaRow}>
              <span className={styles.metaItem}>
                <Bot className={styles.metaIcon} />
                {getAgentName(conversation.agent_id)}
              </span>
              <span>Created {formatDate(conversation.created_at)}</span>
              {conversation.description && (
                <span className={styles.description}>
                  {conversation.description}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className={styles.actions}>
          <Button variant="ghost" size="icon" onClick={handleStartEdit} title="Edit conversation">
            <Pencil style={{ height: "1rem", width: "1rem" }} />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className={styles.dangerButton}
            onClick={() => setIsDeleteDialogOpen(true)}
            title="Delete conversation"
          >
            <Trash2 style={{ height: "1rem", width: "1rem" }} />
          </Button>
        </div>
      </div>

      {error && (
        <div style={{
          padding: "0.75rem 1rem",
          borderRadius: "0.5rem",
          backgroundColor: "rgba(239, 68, 68, 0.1)",
          border: "1px solid rgba(239, 68, 68, 0.2)",
          color: "#f87171",
          fontSize: "0.875rem",
        }}>
          {error}
        </div>
      )}

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

      <Card style={{
        display: "flex",
        flexDirection: "column",
        height: isExpanded ? "100vh" : "calc(100vh - 9rem)",
        minHeight: isExpanded ? undefined : "42rem",
        overflow: "hidden",
        border: "none",
        boxShadow: "none",
        background: "transparent",
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
          background: "#050506",
        } : {}),
      }}>
        <div style={{
          flexShrink: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          width: "min(100%, 56rem)",
          margin: "0 auto",
          padding: "0.25rem 0 0.5rem",
          backgroundColor: "transparent",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", color: "var(--text-muted)", fontSize: "0.8125rem" }}>
            <span>{messages.length} messages</span>
          </div>
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
        </div>
        <CardContent style={{ flex: 1, display: "flex", flexDirection: "column", padding: 0, overflow: "hidden" }}>
          {/* Messages Area */}
          <div
            ref={messagesContainerRef}
            onScroll={handleScroll}
            className={styles.messagesPane}
            style={{
              flex: 1,
              overflowY: "auto",
              padding: "2rem 1rem 1.5rem",
              display: "flex",
              flexDirection: "column",
              gap: "1.55rem",
              width: "min(100%, 56rem)",
              margin: "0 auto",
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
                <p style={{ fontSize: "0.875rem" }}>
                  Send a message{supportsImageGeneration ? " or generate an image" : ""} to start the conversation
                </p>
              </div>
            ) : (
              <>
                <ChatStreamRenderer
                  messages={messages}
                  streamingContent={streamingContent}
                  toolActivities={toolActivities}
                  statusMessage={statusMessage}
                  userPicture={userInfo?.picture}
                  userName={userInfo?.name}
                  extraNode={
                    <>
                      {activeForm && (
                        <div
                          style={{
                            display: "flex",
                            gap: "0.75rem",
                            alignItems: "flex-start",
                          }}
                        >
                          <div style={{
                            display: "none",
                          }} />
                          <div style={{
                            width: "100%",
                            padding: "0.75rem 1rem",
                            borderRadius: "0.875rem",
                            backgroundColor: "rgba(255, 255, 255, 0.055)",
                            color: "var(--text-primary)",
                          }}>
                            <ChatFormRenderer
                              form={activeForm.form}
                              submitLabel={activeForm.submitLabel}
                              onSubmit={handleFormSubmit}
                              onCancel={() => setActiveForm(null)}
                              disabled={isSending || Boolean(pendingFormLabel)}
                            />
                          </div>
                        </div>
                      )}

                      {pendingFormLabel && (
                        <div
                          style={{
                            display: "flex",
                            gap: "0.75rem",
                            alignItems: "flex-start",
                          }}
                        >
                          <div style={{
                            display: "none",
                          }} />
                          <div style={{
                            padding: "0.75rem 1rem",
                            borderRadius: "0.875rem",
                            backgroundColor: "rgba(255, 255, 255, 0.055)",
                            color: "var(--text-secondary)",
                            fontSize: "0.875rem",
                          }}>
                            Captured "{pendingFormLabel}". Processing...
                          </div>
                        </div>
                      )}

                      {streamingImagePreview && (
                        <div
                          style={{
                            display: "flex",
                            gap: "0.75rem",
                            alignItems: "flex-start",
                          }}
                        >
                          <div style={{
                            display: "none",
                          }} />
                          <div style={{
                            width: "100%",
                            padding: "0.875rem",
                            borderRadius: "0.875rem",
                            backgroundColor: "rgba(255, 255, 255, 0.055)",
                            color: "var(--text-primary)",
                          }}>
                            <div style={{ fontWeight: 650, marginBottom: "0.75rem" }}>
                              Generating image: {streamingImagePreview.prompt}
                            </div>
                            <div style={{
                              minHeight: "18rem",
                              borderRadius: "0.75rem",
                              border: "1px solid var(--border-subtle)",
                              backgroundColor: "var(--bg-tertiary)",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              overflow: "hidden",
                              position: "relative",
                            }}>
                              {streamingImagePreview.dataUrl ? (
                                <img
                                  src={streamingImagePreview.dataUrl}
                                  alt={streamingImagePreview.prompt}
                                  style={{
                                    width: "100%",
                                    maxHeight: "34rem",
                                    objectFit: "contain",
                                    animation: "fade-in 250ms ease-out",
                                  }}
                                />
                              ) : (
                                <div style={{
                                  display: "flex",
                                  flexDirection: "column",
                                  alignItems: "center",
                                  gap: "0.75rem",
                                  color: "var(--text-muted)",
                                }}>
                                  <Loader2 style={{ height: "1.5rem", width: "1.5rem", animation: "spin 1s linear infinite" }} />
                                  <span>{streamingImagePreview.status}</span>
                                </div>
                              )}
                              {streamingImagePreview.dataUrl && (
                                <div style={{
                                  position: "absolute",
                                  left: 0,
                                  right: 0,
                                  bottom: 0,
                                  padding: "0.75rem 1rem",
                                  background: "linear-gradient(to top, rgba(0,0,0,0.62), rgba(0,0,0,0))",
                                  color: "white",
                                  fontSize: "0.875rem",
                                }}>
                                  {streamingImagePreview.status}
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      )}
                    </>
                  }
                />
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

          {/* Attachment chips display */}
          {attachments.length > 0 && (
            <div style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "0.5rem",
              padding: "0.5rem 1rem",
              borderTop: "1px solid var(--border-subtle)",
            }}>
              {attachments.map((att, idx) => (
                <AttachmentChip
                  key={idx}
                  filename={att.filename}
                  size={att.size}
                  onRemove={() => removeAttachment(idx)}
                />
              ))}
            </div>
          )}

          {/* Attachment error */}
          {attachmentError && (
            <div style={{
              padding: "0.5rem 1rem",
              color: "#f87171",
              fontSize: "0.75rem",
            }}>
              {attachmentError}
            </div>
          )}

          {/* Input Area */}
          <div style={{
            display: "flex",
            gap: "0.75rem",
            width: "min(100%, 56rem)",
            margin: "0 auto",
            padding: "0.75rem 1rem 1rem",
            alignItems: "flex-end",
            backgroundColor: "transparent",
          }}>
            {/* Hidden file input */}
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept={ALLOWED_EXTENSIONS.join(",")}
              onChange={(e) => e.target.files && addFiles(e.target.files)}
              style={{ display: "none" }}
            />

            {/* Attachment button */}
            <Button
              variant="ghost"
              size="icon"
              onClick={() => fileInputRef.current?.click()}
              disabled={isSending}
              title="Attach files"
              style={{ flexShrink: 0, height: "2.75rem", width: "2.75rem", borderRadius: "999px" }}
            >
              <Paperclip style={{ height: "1rem", width: "1rem" }} />
            </Button>

            {supportsImageGeneration && (
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setIsImageDialogOpen(true)}
                disabled={isSending || isGeneratingImage}
                title="Generate image"
                style={{ flexShrink: 0, height: "2.75rem", width: "2.75rem", borderRadius: "999px" }}
              >
                <ImageIcon style={{ height: "1rem", width: "1rem" }} />
              </Button>
            )}

            <Textarea
              placeholder="Type your message... (Enter to send, Shift+Enter for new line)"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyPress}
              onPaste={handleChatPaste}
              disabled={isSending}
              rows={1}
              style={{
                flex: 1,
                minHeight: "2.75rem",
                maxHeight: "10rem",
                resize: "none",
                overflow: "auto",
                border: "none",
                borderRadius: "1.375rem",
                backgroundColor: "#242427",
                color: "var(--text-primary)",
                padding: "0.75rem 1rem",
                boxShadow: "none",
              }}
              onInput={(e) => {
                const target = e.target as HTMLTextAreaElement;
                target.style.height = "auto";
                target.style.height = Math.min(target.scrollHeight, 160) + "px";
              }}
            />
            <Button
              onClick={() => handleSendMessage()}
              disabled={(!inputValue.trim() && attachments.length === 0) || isSending}
              style={{ flexShrink: 0, height: "2.75rem", width: "2.75rem", borderRadius: "999px", padding: 0 }}
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

      <Dialog open={isEditing} onOpenChange={(open) => open ? handleStartEdit() : handleCancelEdit()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Conversation</DialogTitle>
            <DialogDescription>
              Update the conversation title, description, or assigned agent.
            </DialogDescription>
          </DialogHeader>
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
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
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={handleCancelEdit} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button
              onClick={handleUpdate}
              disabled={!editTitle.trim() || !editAgentId || isSubmitting}
            >
              {isSubmitting ? "Saving..." : "Save Changes"}
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

      <Dialog open={isImageDialogOpen} onOpenChange={setIsImageDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Generate Image</DialogTitle>
            <DialogDescription>
              Describe the image this agent should create.
            </DialogDescription>
          </DialogHeader>
          <Textarea
            value={imagePrompt}
            onChange={(e) => setImagePrompt(e.target.value)}
            placeholder="A clean product hero image for..."
            rows={5}
            disabled={isGeneratingImage}
          />
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsImageDialogOpen(false)}
              disabled={isGeneratingImage}
            >
              Cancel
            </Button>
            <Button
              onClick={handleGenerateImage}
              disabled={!imagePrompt.trim() || isGeneratingImage}
            >
              {isGeneratingImage ? "Generating..." : "Generate"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={imagePasteWarningOpen} onOpenChange={setImagePasteWarningOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Image Attachments Unavailable</DialogTitle>
            <DialogDescription>
              This agent's selected model does not support image attachments. Choose a multimodal model to attach images.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button onClick={() => setImagePasteWarningOpen(false)}>OK</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
