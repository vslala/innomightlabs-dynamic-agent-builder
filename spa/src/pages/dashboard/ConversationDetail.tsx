import { useEffect, useState, useRef } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { ArrowDown, ChevronLeft, Loader2, MessageSquare } from "lucide-react";
import { ChatFormRenderer, type FormAnswer } from "../../components/chat/ChatFormRenderer";
import { CanvasSidePanel } from "../../components/chat/CanvasSidePanel";
import { ChatComposer } from "../../components/chat/ChatComposer";
import { TokenUsageIndicator, type LiveTokenUsageUpdate } from "../../components/chat/TokenUsageIndicator";
import { ChatStreamRenderer } from "../../components/chat/ChatStreamRenderer";
import { COMPACT_QUERY } from "../../components/dashboard/breakpoints";
import { featureFlags } from "../../config/featureFlags";
import { useFileAttachments } from "../../hooks/useFileAttachments";
import { useConversationImages } from "../../hooks/useConversationImages";
import { useConversationDocuments } from "../../hooks/useConversationDocuments";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { useStickToBottom } from "../../hooks/useStickToBottom";
import { CHAT_DOCUMENT_EXTENSIONS, readsOnlyAsDocument } from "../../lib/documents";
import { cn } from "../../lib/utils";
import { ALLOWED_EXTENSIONS } from "../../types/message";
import { Button } from "../../components/ui/button";
import { ConfirmationDialog } from "../../components/ui/confirmation-dialog";
import { FileInput } from "../../components/ui/file-input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";
import { conversationApiService } from "../../services/conversations";
import { agentApiService, type AgentResponse } from "../../services/agents/AgentApiService";
import { agentDisplayName, isIla, showsToolActivity } from "../../services/builder/ila";
import { connectedMessage } from "../../services/builder/connect";
import { ConnectAccountCard, type ConnectRequestPayload } from "../../components/chat/ConnectAccountCard";
import { ConsentCard } from "../../components/chat/consent/ConsentCard";
import { IlaWorking } from "../../components/chat/IlaWorking";
import { ilaStatus } from "../../components/chat/ilaStatus";
import { chatService, type ActiveTurn } from "../../services/chat";
import { authService } from "../../services/auth";
import type { ConsentDecision, ConsentRequest } from "../../types/consent";
import type { ConversationResponse } from "../../types/conversation";
import type { FormSchema } from "../../types/form";
import {
  SSEEventType,
  type Message,
  type MessageCanvasArtifact,
  type MessageConsent,
  type SSEEvent,
  type ToolActivity,
} from "../../types/message";
import { ConversationTopBar } from "./conversations/detail/ConversationTopBar";
import { ComposerAttachments } from "./conversations/detail/ComposerAttachments";
import { EditConversationDialog, type ConversationEdits } from "./conversations/detail/EditConversationDialog";
import { GenerateImageDialog } from "./conversations/detail/GenerateImageDialog";
import { StreamingImagePreview, type StreamingImage } from "./conversations/detail/StreamingImagePreview";
import {
  appendOnce,
  consentDecisionContent,
  formAwaitingAnswer,
  formSubmissionContent,
  generatedImageMessage,
  liveTokenUsageFrom,
  mergeLatestPage,
  partialImageDataUrl,
} from "./conversations/detail/turnMessages";
import { useAppResume } from "../../hooks/useAppResume";
import parts from "./conversations/detail/ConversationParts.module.css";
import styles from "./Conversation.module.css";

interface ConversationNavigationState {
  initialImagePrompt?: string;
  initialMessage?: string;
  /** Files picked on the start page: uploaded here, with the message left in the composer to send. */
  initialFiles?: File[];
  debug?: boolean;
}

const MESSAGES_PAGE_SIZE = 20;
/** Scrolled this close to the top, the next page of older messages loads. */
const LOAD_OLDER_THRESHOLD_PX = 50;
const CONVERSATIONS_PATH = "/dashboard/conversations";

export function ConversationDetail() {
  const { conversationId } = useParams<{ conversationId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [conversation, setConversation] = useState<ConversationResponse | null>(null);
  const [agents, setAgents] = useState<AgentResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Decoded once: the token does not change while the page is open, and this renders on every streamed chunk
  const [userInfo] = useState(() => authService.getUserFromToken());
  const compact = useMediaQuery(COMPACT_QUERY);

  const [isEditing, setIsEditing] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  // Chat state
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [activeTurnId, setActiveTurnId] = useState<string | null>(null);
  const [streamingContent, setStreamingContent] = useState("");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [activeForm, setActiveForm] = useState<{ form: FormSchema; submitLabel?: string; leadForm?: string } | null>(null);
  /** Shows again the form a reopened chat was left on, such as a plan's approval, so it can still be answered. */
  const showFormAwaitingAnswer = (transcript: Message[]) => {
    const waiting = formAwaitingAnswer(transcript);
    if (waiting) setActiveForm({ form: waiting.form, submitLabel: waiting.submit_label, leadForm: waiting.lead_form });
  };

  const [activeConnect, setActiveConnect] = useState<ConnectRequestPayload | null>(null);
  // Consent cards by id, as they stand now: messages say which they raised, this says what became of them
  const [consents, setConsents] = useState<Record<string, ConsentRequest>>({});
  const [chatError, setChatError] = useState<string | null>(null);
  const [toolActivities, setToolActivities] = useState<ToolActivity[]>([]);
  const [liveTokenUsage, setLiveTokenUsage] = useState<LiveTokenUsageUpdate | null>(null);
  const [incompleteResponse, setIncompleteResponse] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isImageDialogOpen, setIsImageDialogOpen] = useState(false);
  const [expandedCanvas, setExpandedCanvas] = useState<MessageCanvasArtifact | null>(null);
  const [debugEnabled, setDebugEnabled] = useState(
    () => Boolean((location.state as ConversationNavigationState | null)?.debug)
  );
  const [isGeneratingImage, setIsGeneratingImage] = useState(false);
  const [streamingImagePreview, setStreamingImagePreview] = useState<StreamingImage | null>(null);
  const transcript = useStickToBottom();
  const streamingContentRef = useRef("");
  const latestImagePreviewDataUrlRef = useRef<string | null>(null);
  const hadToolCallsRef = useRef(false);
  const renderedFormRef = useRef(false);
  const assistantMessageSavedRef = useRef(false);
  const pendingCanvasArtifactsRef = useRef<MessageCanvasArtifact[]>([]);
  const pendingConsentsRef = useRef<MessageConsent[]>([]);
  const initialMessageSentRef = useRef(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const documentInputRef = useRef<HTMLInputElement>(null);
  const streamAbortRef = useRef<AbortController | null>(null);
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
        conversationApiService.getMessages(conversationId, MESSAGES_PAGE_SIZE),
      ]);
      setConversation(conversationData);
      setAgents(agentsData);
      // Messages come newest-first, reverse for display (oldest at top)
      const transcript = messagesData.items.reverse();
      setMessages(transcript);
      showFormAwaitingAnswer(transcript);
      setMessagesCursor(messagesData.next_cursor);
      setHasMoreMessages(messagesData.has_more);
      setInitialMessagesLoaded(true);
      void loadConsents(conversationData.agent_id, conversationId);
    } catch (err) {
      setError("Failed to load conversation. It may not exist or you don't have access.");
      console.error("Error loading conversation:", err);
    } finally {
      setLoading(false);
    }
  };

  const loadConsents = async (agentId: string, id: string) => {
    try {
      const cards = await chatService.listConsents(agentId, id);
      setConsents(Object.fromEntries(cards.map((card) => [card.consent_id, card])));
    } catch (err) {
      console.error("Failed to load the conversation's approvals:", err);
    }
  };

  const keepConsent = (card: ConsentRequest) => setConsents((current) => ({ ...current, [card.consent_id]: card }));

  // Load older messages (for infinite scroll up)
  const loadOlderMessages = async () => {
    if (!conversationId || !messagesCursor || isLoadingMessages) return;

    setIsLoadingMessages(true);
    try {
      const messagesData = await conversationApiService.getMessages(conversationId, MESSAGES_PAGE_SIZE, messagesCursor);

      // Save scroll position to restore after prepending
      const container = transcript.scrollElement.current;
      const previousScrollHeight = container?.scrollHeight || 0;

      // Prepend older messages (reverse them for display order)
      setMessages((prev) => [...messagesData.items.reverse(), ...prev]);
      setMessagesCursor(messagesData.next_cursor);
      setHasMoreMessages(messagesData.has_more);

      // Restore scroll position after DOM update
      requestAnimationFrame(() => {
        if (container) {
          container.scrollTop = container.scrollHeight - previousScrollHeight;
        }
      });
    } catch (err) {
      console.error("Error loading older messages:", err);
    } finally {
      setIsLoadingMessages(false);
    }
  };

  const handleScroll = () => {
    transcript.onScroll();
    const container = transcript.scrollElement.current;
    if (!container || isLoadingMessages || !hasMoreMessages) return;
    if (container.scrollTop < LOAD_OLDER_THRESHOLD_PX) {
      void loadOlderMessages();
    }
  };

  // A first page too short to scroll can never be scrolled up, so the older ones load on their own
  useEffect(() => {
    if (!initialMessagesLoaded || isLoadingMessages || !hasMoreMessages) return;

    const container = transcript.scrollElement.current;
    if (!container) return;

    if (container.scrollHeight <= container.clientHeight + 8) {
      void loadOlderMessages();
    }
  }, [initialMessagesLoaded, messages.length, hasMoreMessages, isLoadingMessages]);

  useEffect(() => {
    initialMessageSentRef.current = false;
    loadData();

    // Stop reading the stream when navigating away or switching conversations.
    // The server-side turn keeps running either way — see
    // api/docs/LLD-async-chat-turns.md. The reattach effect below picks it back
    // up if this conversation still has one running.
    return () => {
      streamAbortRef.current?.abort();
      streamAbortRef.current = null;
      finishTurn();
      resetTurnUiState();
    };
  }, [conversationId]);

  // Reattach to a turn still running for this conversation — covers navigating
  // back and a full page refresh identically, since both start from scratch here.
  // Back from the background (a phone locks, another tab): the stream may have died meanwhile. A turn still
  // running is followed again unless this page is still following it (followTurn retries a dropped stream);
  // otherwise the newest page brings in what finished, and approvals decided elsewhere.
  const resyncAfterResume = async () => {
    if (!conversation || !initialMessagesLoaded) return;
    const { agent_id, conversation_id } = conversation;
    try {
      const active = await chatService.getActiveTurn(agent_id, conversation_id);
      if (active?.status === "running") {
        if (!(isSending && activeTurnId === active.turn_id)) void attachToTurn(active.turn_id, "");
        return;
      }
      if (isSending) finishTurn();
      const latest = await conversationApiService.getMessages(conversation_id, MESSAGES_PAGE_SIZE);
      const page = latest.items.reverse();
      setMessages((current) => mergeLatestPage(current, page));
      showFormAwaitingAnswer(page);
      void loadConsents(agent_id, conversation_id);
    } catch (err) {
      console.error("Failed to resync the conversation:", err);
    }
  };
  useAppResume(() => void resyncAfterResume());

  useEffect(() => {
    if (!conversation || !initialMessagesLoaded) return;
    let cancelled = false;

    (async () => {
      let active: ActiveTurn | null = null;
      try {
        active = await chatService.getActiveTurn(conversation.agent_id, conversation.conversation_id);
      } catch (err) {
        console.error("Failed to check for an in-progress response:", err);
        return;
      }
      if (cancelled || !active || active.status !== "running") return;
      void attachToTurn(active.turn_id, "");
    })();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversation?.conversation_id, initialMessagesLoaded]);

  useEffect(() => {
    const state = location.state as ConversationNavigationState | null;
    const initialImagePrompt = state?.initialImagePrompt?.trim();
    const initialMessage = state?.initialMessage?.trim();
    if (
      (!initialMessage && !initialImagePrompt) ||
      initialMessageSentRef.current ||
      !conversation ||
      !initialMessagesLoaded ||
      isSending ||
      isGeneratingImage
    ) {
      return;
    }

    initialMessageSentRef.current = true;
    navigate(`${CONVERSATIONS_PATH}/${conversation.conversation_id}`, {
      replace: true,
      state: null,
    });
    if (initialImagePrompt) {
      void handleGenerateImage(initialImagePrompt);
    } else if (initialMessage && state?.initialFiles?.length) {
      // The uploads have to finish before the message can go, so the user sends it
      setInputValue(initialMessage);
      handleFiles(state.initialFiles);
    } else if (initialMessage) {
      void handleSendMessage(initialMessage);
    }
  }, [conversation, initialMessagesLoaded, isGeneratingImage, isSending, location.state, navigate]);

  // Full screen is a desktop affordance; on compact screens the conversation already fills the screen
  const expanded = isExpanded && !compact;

  useEffect(() => {
    if (!expanded) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsExpanded(false);
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [expanded]);

  const isIlaConversation = isIla(conversation?.agent_id);
  // Ila shows the tool she's running as one line instead of a list, then the next; it steps aside once her reply streams in.
  const ilaWorkingStatus = isIlaConversation ? ilaStatus(toolActivities, isSending && !streamingContent) : null;

  const currentAgent = conversation
    ? agents.find((agent) => agent.agent_id === conversation.agent_id)
    : null;
  const supportsImageGeneration = currentAgent?.capabilities?.includes("image_generation") ?? false;
  const images = useConversationImages(conversationId, conversation?.agent_id);
  const documents = useConversationDocuments(conversationId);

  const handleUpdate = async (edits: ConversationEdits) => {
    if (!conversationId) return;
    setConversation(await conversationApiService.updateConversation(conversationId, edits));
  };

  const handleDelete = async () => {
    if (!conversationId) return;

    setIsDeleting(true);
    try {
      await conversationApiService.deleteConversation(conversationId);
      navigate(CONVERSATIONS_PATH);
    } catch (err) {
      console.error("Error deleting conversation:", err);
      setIsDeleting(false);
    }
  };

  // Transient turn UI (streaming text, tool activity, forms, image preview) — not
  // the persisted message list, which loadData()/setMessages own separately.
  const resetTurnUiState = () => {
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
    pendingCanvasArtifactsRef.current = [];
    pendingConsentsRef.current = [];
  };

  const finishTurn = () => {
    setIsSending(false);
    setStatusMessage(null);
    setActiveTurnId(null);
  };

  const clearImagePreview = () => {
    latestImagePreviewDataUrlRef.current = null;
    setStreamingImagePreview(null);
  };

  const showPartialImage = (event: SSEEvent, prompt: string) => {
    const dataUrl = partialImageDataUrl(event);
    if (!dataUrl) return;
    latestImagePreviewDataUrlRef.current = dataUrl;
    setStreamingImagePreview({ prompt, dataUrl, status: "Painting preview..." });
  };

  const trackTokenUsage = (event: SSEEvent) => {
    const usage = liveTokenUsageFrom(event);
    if (usage) setLiveTokenUsage(usage);
  };

  interface TurnEventContext {
    conversationId: string;
    /** The optimistic temp id to reconcile once the real user message is saved. */
    optimisticUserMessageId: string;
    imageLabel: string;
    finish: () => void;
  }

  // Fetches a message the backend already confirmed saving but that never
  // rendered live (an SSE event was dropped somewhere between the server and
  // this tab). Keeps the live view from permanently diverging from what a
  // page refresh would show.
  const recoverMissingAssistantMessage = async (conversationId: string, messageId: string) => {
    try {
      const page = await conversationApiService.getMessages(conversationId, 5);
      const recovered = page.items.find((m) => m.message_id === messageId);
      if (!recovered) return;
      setMessages((prev) => appendOnce(prev, recovered));
    } catch (err) {
      console.error("Failed to recover a saved assistant message the stream did not deliver:", err);
    }
  };

  // Applies one SSE event to chat UI state. Shared by a fresh send and by
  // reattaching to a turn still running server-side, so the two render
  // identically — see api/docs/LLD-async-chat-turns.md.
  const applyTurnEvent = (event: SSEEvent, ctx: TurnEventContext) => {
    switch (event.event_type) {
      case SSEEventType.LIFECYCLE_NOTIFICATION:
        setStatusMessage(event.content);
        setStreamingImagePreview((prev) => (prev ? { ...prev, status: event.content } : prev));
        break;

      case SSEEventType.AGENT_RESPONSE_TO_USER:
        setStatusMessage(null);
        streamingContentRef.current += event.content;
        setStreamingContent(streamingContentRef.current);
        break;

      case SSEEventType.UI_FORM_RENDER:
        if (event.form) {
          renderedFormRef.current = true;

          setActiveForm({
            form: event.form,
            submitLabel: event.submit_label || undefined,
            leadForm: event.lead_form || undefined,
          });
        }
        break;

      case SSEEventType.CONNECT_REQUEST:
        if (event.connect) setActiveConnect(event.connect);
        break;

      case SSEEventType.CONSENT_REQUEST:
        if (event.consent) {
          keepConsent(event.consent);
          pendingConsentsRef.current.push({ consent_id: event.consent.consent_id, title: event.consent.title });
        }
        break;

      case SSEEventType.CONSENT_UPDATED:
        if (event.consent) keepConsent(event.consent);
        break;

      case SSEEventType.CANVAS_ARTIFACT_READY:
        if (event.canvas_artifact_id) {
          pendingCanvasArtifactsRef.current.push({
            artifact_id: event.canvas_artifact_id,
            title: event.canvas_title || "Canvas",
            mime_type: event.canvas_mime_type || "text/html",
            caption: event.canvas_caption,
            content_url: event.canvas_content_url,
          });
        }
        break;

      case SSEEventType.IMAGE_GENERATION_STARTED:
        latestImagePreviewDataUrlRef.current = null;
        setStatusMessage(event.content);
        setStreamingImagePreview({
          prompt: ctx.imageLabel || "Generated image",
          dataUrl: null,
          status: event.content,
        });
        break;

      case SSEEventType.IMAGE_GENERATION_PARTIAL:
        if (event.image_b64) {
          setStatusMessage(null);
          showPartialImage(event, ctx.imageLabel || "Generated image");
        }
        break;

      case SSEEventType.IMAGE_GENERATION_COMPLETE:
        if (event.images?.length) {
          assistantMessageSavedRef.current = true;
          const message = generatedImageMessage({
            messageId: event.message_id || `assistant-image-${Date.now()}`,
            conversationId: ctx.conversationId,
            prompt: ctx.imageLabel,
            images: event.images,
            previewDataUrl: latestImagePreviewDataUrlRef.current,
          });
          setMessages((prev) => appendOnce(prev, message));
        }
        clearImagePreview();
        setStatusMessage(null);
        break;

      case SSEEventType.USER_MESSAGE_SAVED:
        // Reconcile the optimistic temp id with the real one. On reattach there
        // is no matching temp message (the real one already came from history),
        // so this is a harmless no-op.
        if (event.message_id) {
          setMessages((prev) =>
            prev.map((m) =>
              m.message_id === ctx.optimisticUserMessageId
                ? { ...m, message_id: event.message_id! }
                : m
            )
          );
        }
        break;

      case SSEEventType.ASSISTANT_MESSAGE_SAVED:
        // The backend confirms the message is persisted regardless of what we
        // managed to render live, so this is authoritative independent of the
        // branch below — see the STREAM_COMPLETE case, which used to treat a
        // dropped event here as "the agent never finished".
        assistantMessageSavedRef.current = true;
        if (streamingContentRef.current) {
          // Snapshot the refs now: React runs the updater later, after
          // STREAM_COMPLETE (often in the same chunk) has already cleared them.
          const message: Message = {
            message_id: event.message_id || `assistant-${Date.now()}`,
            conversation_id: ctx.conversationId,
            role: "assistant",
            content: streamingContentRef.current,
            canvases: pendingCanvasArtifactsRef.current.length ? pendingCanvasArtifactsRef.current : undefined,
            consents: pendingConsentsRef.current.length ? pendingConsentsRef.current : undefined,
            created_at: new Date().toISOString(),
          };
          setMessages((prev) => appendOnce(prev, message));
        } else if (event.message_id) {
          // We have nothing accumulated to render, yet the backend says a
          // message was saved -- almost always because an earlier event (often
          // this message's own streamed text) never reached the client even
          // though it was written. Recover what was actually persisted rather
          // than silently dropping a message the user would otherwise only
          // see after a manual refresh.
          void recoverMissingAssistantMessage(ctx.conversationId, event.message_id);
        }
        pendingCanvasArtifactsRef.current = [];
        pendingConsentsRef.current = [];
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
        clearImagePreview();
        ctx.finish();
        break;

      case SSEEventType.TOOL_CALL_START:
        hadToolCallsRef.current = true;
        if (event.tool_name) {
          const activity: ToolActivity = {
            id: `tool-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`,
            timestamp: new Date(),
            tool_call_id: event.tool_call_id,
            tool_name: event.tool_name,
            status: "running",
            content: event.content,
            tool_args: event.tool_args,
            display_tool_name: event.display_tool_name,
            display_tool_args: event.display_tool_args,
          };
          setToolActivities((prev) => [...prev, activity]);
        }
        break;

      case SSEEventType.TOOL_CALL_RESULT:
        if (event.tool_name) {
          setToolActivities((prev) => {
            // Match by tool_call_id first: tool_name alone isn't unique when
            // the same tool is called more than once in a turn, which used to
            // let a result pair with the wrong still-running call. Fall back
            // to the old name+running heuristic only if either side lacks an
            // id (e.g. a transcript replayed across a deploy boundary).
            const byId = event.tool_call_id
              ? prev.findIndex((activity) => activity.tool_call_id === event.tool_call_id)
              : -1;
            const matchIndex =
              byId >= 0
                ? byId
                : prev.findIndex(
                    (activity) => activity.tool_name === event.tool_name && activity.status === "running"
                  );
            if (matchIndex < 0) return prev;
            return prev.map((activity, index) =>
              index === matchIndex
                ? { ...activity, status: event.success ? "success" : "error", content: event.content }
                : activity
            );
          });
        }
        break;

      case SSEEventType.TOKEN_USAGE_UPDATE:
        trackTokenUsage(event);
        break;

      case SSEEventType.ERROR:
        setChatError(event.content);
        clearImagePreview();
        ctx.finish();
        break;

      default:
        break;
    }
  };

  /** Starts reading a new stream, abandoning (not stopping) any earlier one. */
  const startStream = () => {
    streamAbortRef.current?.abort();
    const controller = new AbortController();
    streamAbortRef.current = controller;
    return controller.signal;
  };

  // Reattach to a turn that is still running (or just finished) server-side —
  // on navigating back, on a full page refresh, and on a 409 conflict from
  // handleSendMessage when another tab already started one.
  const attachToTurn = async (turnId: string, imageLabel: string) => {
    if (!conversation) return;

    resetTurnUiState();
    setActiveTurnId(turnId);
    setIsSending(true);

    const ctx: TurnEventContext = {
      conversationId: conversation.conversation_id,
      optimisticUserMessageId: "",
      imageLabel,
      finish: finishTurn,
    };

    await chatService.followTurn(conversation.agent_id, conversation.conversation_id, turnId, {
      onEvent: (event) => applyTurnEvent(event, ctx),
      signal: startStream(),
      onError: (err) => {
        setChatError(err.message);
        finishTurn();
      },
      onComplete: finishTurn,
    });
  };

  const handleStopTurn = async () => {
    if (!conversation || !activeTurnId) return;
    try {
      await chatService.stopTurn(conversation.agent_id, conversation.conversation_id, activeTurnId);
    } catch (err) {
      console.error("Failed to stop the response:", err);
    }
  };

  // What the composer holds, and whether an upload is still on its way: the send button and the handler both ask
  const composerHasContent =
    Boolean(inputValue.trim()) || attachments.length > 0 || images.readyImageIds.length > 0 || documents.documents.length > 0;
  const uploadsInProgress = images.isUploading || images.hasFailed || documents.uploading.length > 0;

  /** Shows the person's message straight away and follows the transcript to it. */
  const addOptimisticMessage = async (message: Message) => {
    setMessages((prev) => [...prev, message]);
    transcript.scrollToBottom();
    await nextAnimationFrame();
  };

  const handleSendMessage = async (
    messageOverride?: string,
    optimisticUserContent?: string,
  ) => {
    const messageToSend = messageOverride || inputValue.trim();
    const hasContent = Boolean(messageOverride) || composerHasContent;
    if (!hasContent || !conversation || isSending || (!messageOverride && uploadsInProgress)) return;

    // Capture attachments before clearing
    const attachmentsToSend = attachments.length > 0 ? [...attachments] : undefined;
    const imagesToSend = messageOverride ? [] : images.images.filter((image) => image.imageId);
    const referencesToSend = messageOverride ? [] : documents.takeForSending();

    if (!messageOverride) {
      setInputValue("");
      clearAttachments();
      images.clearImages();
    }
    setIsSending(true);
    resetTurnUiState();

    // Add user message to the list immediately (unless it's a retry/continue message)
    const isRetryMessage = messageOverride?.startsWith("Please continue");
    const userMsg: Message = {
      message_id: `temp-${Date.now()}`,
      conversation_id: conversation.conversation_id,
      role: "user",
      content:
        optimisticUserContent ??
        (messageToSend || (imagesToSend.length > 0 || referencesToSend.length > 0 ? "" : "(attachments only)")),
      attachments: attachmentsToSend?.map((a) => ({ filename: a.filename, size: a.size })),
      // Shown from the local files until the saved message arrives; the server reports the real dimensions.
      image_attachments: imagesToSend.map((image) => ({
        image_id: image.imageId ?? image.localId,
        filename: image.file.name,
        mime_type: image.file.type,
        size_bytes: image.file.size,
        width: 0,
        height: 0,
        url: image.previewUrl,
      })),
      references: referencesToSend,
      created_at: new Date().toISOString(),
    };
    if (!isRetryMessage) {
      await addOptimisticMessage(userMsg);
    }

    const ctx: TurnEventContext = {
      conversationId: conversation.conversation_id,
      optimisticUserMessageId: userMsg.message_id,
      imageLabel: messageToSend,
      finish: finishTurn,
    };

    await chatService.sendMessage(
      conversation.agent_id,
      conversation.conversation_id,
      {
        content: messageToSend || "",
        attachments: attachmentsToSend,
        imageIds: imagesToSend.flatMap((image) => (image.imageId ? [image.imageId] : [])),
        references: referencesToSend,
      },
      {
        onEvent: (event) => applyTurnEvent(event, ctx),
        signal: startStream(),
        onTurnStarted: setActiveTurnId,
        onConflict: (runningTurnId) => {
          if (!isRetryMessage) {
            setMessages((prev) => prev.filter((m) => m.message_id !== userMsg.message_id));
          }
          void attachToTurn(runningTurnId, messageToSend);
        },
        onError: (err) => {
          setChatError(err.message);
          finishTurn();
        },
        onComplete: finishTurn,
      }
    );
  };

  // The person's decision on a card: the turn that carries on from it streams back like a message's
  const handleDecideConsent = async (card: ConsentRequest, decision: ConsentDecision) => {
    if (!conversation || isSending) return;
    setIsSending(true);
    resetTurnUiState();

    const userMsg: Message = {
      message_id: `temp-${Date.now()}`,
      conversation_id: conversation.conversation_id,
      role: "user",
      content: consentDecisionContent(card, decision),
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    transcript.scrollToBottom();

    const ctx: TurnEventContext = {
      conversationId: conversation.conversation_id,
      optimisticUserMessageId: userMsg.message_id,
      imageLabel: "",
      finish: finishTurn,
    };

    let refused: Error | null = null;
    await chatService.decideConsent(conversation.agent_id, conversation.conversation_id, card.consent_id, decision, {
      onEvent: (event) => applyTurnEvent(event, ctx),
      signal: startStream(),
      onTurnStarted: setActiveTurnId,
      onConflict: (runningTurnId) => {
        setMessages((prev) => prev.filter((m) => m.message_id !== userMsg.message_id));
        void attachToTurn(runningTurnId, "");
      },
      onError: (err) => {
        refused = err;
        setMessages((prev) => prev.filter((m) => m.message_id !== userMsg.message_id));
        finishTurn();
      },
      onComplete: finishTurn,
    });
    // The card shows why it didn't go through, and can be decided again
    if (refused) throw refused;
  };

  const renderConsent = (raised: MessageConsent) => {
    const card = consents[raised.consent_id];
    if (!card) return null;
    return (
      <ConsentCard
        consent={card}
        agentName={currentAgent?.agent_name}
        disabled={isSending}
        onDecide={(decision) => handleDecideConsent(card, decision)}
      />
    );
  };

  // Handle retry for incomplete responses
  const handleRetry = () => {
    setIncompleteResponse(false);
    handleSendMessage("Please continue your response from where you left off.");
  };

  /** Lead forms take files, uploaded against the stored form; forms the agent made up have nothing to check them against. */
  const uploadLeadFileFor = (leadForm: string | undefined) =>
    leadForm && conversationId
      ? (inputName: string, file: File) => conversationApiService.uploadLeadFile(conversationId, leadForm, inputName, file)
      : undefined;

  const handleFormSubmit = async (answers: FormAnswer[]) => {
    if (!activeForm) return;
    const label = activeForm.form.form_name;

    await handleSendMessage(formSubmissionContent(label, answers), `Submitted: ${label}`);
  };

  const handleGenerateImage = async (promptValue: string) => {
    if (!conversation || !promptValue.trim() || isGeneratingImage) return;

    const prompt = promptValue.trim();
    setIsGeneratingImage(true);
    setChatError(null);
    setStatusMessage(null);
    latestImagePreviewDataUrlRef.current = null;
    setStreamingImagePreview({
      prompt,
      dataUrl: null,
      status: "Starting image generation...",
    });
    transcript.scrollToBottom();

    const stopGenerating = () => {
      clearImagePreview();
      setIsGeneratingImage(false);
    };
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
                setMessages((prev) => [
                  ...prev,
                  {
                    message_id: event.message_id || `image-user-${Date.now()}`,
                    conversation_id: conversation.conversation_id,
                    role: "user",
                    content: prompt,
                    created_at: new Date().toISOString(),
                  },
                ]);
                break;

              case SSEEventType.IMAGE_GENERATION_STARTED:
              case SSEEventType.LIFECYCLE_NOTIFICATION:
                setStreamingImagePreview((prev) => (prev ? { ...prev, status: event.content } : prev));
                break;

              case SSEEventType.IMAGE_GENERATION_PARTIAL:
                showPartialImage(event, prompt);
                break;

              case SSEEventType.ASSISTANT_MESSAGE_SAVED:
                assistantMessageId = event.message_id || null;
                break;

              case SSEEventType.IMAGE_GENERATION_COMPLETE:
                if (event.images?.length) {
                  const message = generatedImageMessage({
                    messageId: assistantMessageId || event.message_id || `assistant-image-${Date.now()}`,
                    conversationId: conversation.conversation_id,
                    prompt,
                    images: event.images,
                    previewDataUrl: latestImagePreviewDataUrlRef.current,
                  });
                  setMessages((prev) => [...prev, message]);
                }
                clearImagePreview();
                break;

              case SSEEventType.TOKEN_USAGE_UPDATE:
                trackTokenUsage(event);
                break;

              case SSEEventType.ERROR:
                setChatError(event.content);
                stopGenerating();
                break;

              case SSEEventType.STREAM_COMPLETE:
                stopGenerating();
                break;

              default:
                break;
            }
          },
          onError: (err) => {
            setChatError(err.message);
            stopGenerating();
          },
          onComplete: () => {
            setIsGeneratingImage(false);
          },
        }
      );
    } catch (err) {
      setChatError(err instanceof Error ? err.message : String(err));
      stopGenerating();
    } finally {
      setStatusMessage(null);
    }
  };

  /**
   * Files picked or dropped: images go to the image attachments, PDFs, Word and slides to the conversation's
   * documents, the rest to the text-file attachments.
   */
  const handleFiles = (files: File[]) => {
    const rest = images.takeImages(files);
    documents.addDocuments(rest.filter((file) => readsOnlyAsDocument(file.name)));
    const text = rest.filter((file) => !readsOnlyAsDocument(file.name));
    if (text.length > 0) void addFiles(text);
  };

  const backToConversations = () => navigate(CONVERSATIONS_PATH);

  if (loading) {
    return (
      <div className={styles.loadingPanel}>
        <div className={styles.loadingSpinner} />
      </div>
    );
  }

  if (error && !conversation) {
    return (
      <div className={styles.notFound}>
        <Button variant="ghost" size="icon" onClick={backToConversations} aria-label="Back to conversations">
          <ChevronLeft className={styles.notFoundBack} />
        </Button>
        <div className={styles.notFoundBody}>
          <MessageSquare className={styles.notFoundIcon} />
          <h1 className={styles.notFoundTitle}>Conversation not found</h1>
          <p className={styles.notFoundMessage}>{error}</p>
          <Button onClick={backToConversations}>Back to Conversations</Button>
        </div>
      </div>
    );
  }

  if (!conversation) return null;

  const isEmpty = messages.length === 0 && !streamingContent && !statusMessage && !streamingImagePreview;
  const hasAttachments =
    attachments.length > 0 || images.images.length > 0 || documents.documents.length > 0 || documents.uploading.length > 0;
  const composerNotice = attachmentError || images.error || documents.error;

  return (
    <div className={cn(styles.page, expanded && styles.expanded)}>
      <ConversationTopBar
        title={conversation.title}
        agentName={agentDisplayName(agents, conversation.agent_id)}
        description={conversation.description}
        supportsImages={supportsImageGeneration}
        debugEnabled={debugEnabled}
        expanded={compact ? undefined : isExpanded}
        onBack={backToConversations}
        onEdit={() => setIsEditing(true)}
        onDelete={() => setIsDeleteDialogOpen(true)}
        onDebugChange={setDebugEnabled}
        onExpandedChange={setIsExpanded}
      />

      <div className={styles.body}>
        <div className={styles.chat}>
          <div ref={transcript.scrollRef} onScroll={handleScroll} className={styles.messages}>
            <div ref={transcript.contentRef} className={styles.thread}>
              {isLoadingMessages && (
                <div className={styles.olderNotice} role="status">
                  <Loader2 className={styles.inlineSpinner} />
                  Loading older messages...
                </div>
              )}

              {isEmpty ? (
                <div className={styles.emptyState}>
                  <MessageSquare className={styles.emptyIcon} />
                  <p className={styles.emptyTitle}>No messages yet</p>
                  <p className={styles.emptySubtitle}>
                    Send a message{supportsImageGeneration ? " or generate an image" : ""} to start the conversation
                  </p>
                </div>
              ) : (
                <ChatStreamRenderer
                  messages={messages}
                  streamingContent={streamingContent}
                  toolActivities={showsToolActivity(conversation.agent_id, featureFlags.showToolActivity) ? toolActivities : []}
                  debugToolActivity={debugEnabled}
                  statusMessage={isIlaConversation ? null : statusMessage}
                  userPicture={userInfo?.picture}
                  userName={userInfo?.name}
                  onExpandCanvas={setExpandedCanvas}
                  renderConsent={renderConsent}
                  extraNode={
                    (ilaWorkingStatus || activeConnect || activeForm || streamingImagePreview) && (
                      <>
                        {ilaWorkingStatus && <IlaWorking label={ilaWorkingStatus} />}
                        {activeConnect && (
                          <ConnectAccountCard
                            request={activeConnect}
                            disabled={isSending}
                            onConnected={() => {
                              const title = activeConnect.title;
                              setActiveConnect(null);
                              void handleSendMessage(connectedMessage(title));
                            }}
                          />
                        )}
                        {activeForm && (
                          <div className={parts.panel}>
                            <ChatFormRenderer
                              form={activeForm.form}
                              submitLabel={activeForm.submitLabel}
                              onSubmit={handleFormSubmit}
                              onCancel={() => setActiveForm(null)}
                              disabled={isSending}
                              uploadFile={uploadLeadFileFor(activeForm.leadForm)}
                            />
                          </div>
                        )}

                        {streamingImagePreview && <StreamingImagePreview image={streamingImagePreview} />}
                      </>
                    )
                  }
                />
              )}
            </div>
          </div>

          <div className={styles.dock}>
            {!transcript.atBottom && (
              <Button
                variant="secondary"
                size="icon"
                onClick={() => transcript.scrollToBottom("smooth")}
                aria-label="Jump to latest message"
                className={styles.jumpButton}
              >
                <ArrowDown className={styles.jumpIcon} />
              </Button>
            )}

            {chatError && (
              <div className={styles.errorNotice} role="alert">
                {chatError}
              </div>
            )}

            {incompleteResponse && (
              <div className={styles.retryNotice} role="status">
                <span className={styles.retryText}>The agent processed your request but didn't finish responding.</span>
                <Button size="sm" variant="outline" onClick={handleRetry} disabled={isSending} className={styles.retryButton}>
                  {isSending ? "Retrying..." : "Retry"}
                </Button>
              </div>
            )}

            <FileInput
              ref={fileInputRef}
              multiple
              accept={[...ALLOWED_EXTENSIONS, ...images.imageTypes].join(",")}
              onChange={(e) => {
                if (e.target.files) handleFiles(Array.from(e.target.files));
                e.target.value = "";
              }}
            />
            <FileInput
              ref={documentInputRef}
              multiple
              accept={CHAT_DOCUMENT_EXTENSIONS.join(",")}
              onChange={(e) => {
                if (e.target.files) documents.addDocuments(Array.from(e.target.files));
                e.target.value = "";
              }}
            />

            <ChatComposer
              value={inputValue}
              placeholder={`Message ${agentDisplayName(agents, conversation.agent_id)}`}
              onChange={setInputValue}
              onSubmit={() => handleSendMessage()}
              onPaste={images.onPaste}
              onDropFiles={(data) => handleFiles(Array.from(data.files))}
              isSubmitting={isSending}
              attachments={
                hasAttachments && (
                  <ComposerAttachments
                    files={attachments}
                    onRemoveFile={removeAttachment}
                    images={images}
                    documents={documents}
                  />
                )
              }
              notice={composerNotice}
              statusIndicator={<TokenUsageIndicator agentId={conversation.agent_id} liveUsage={liveTokenUsage} />}
              submitDisabled={!composerHasContent || isSending || uploadsInProgress}
              onAttachFiles={() => fileInputRef.current?.click()}
              onAttachDocuments={() => documentInputRef.current?.click()}
              imageAction={
                supportsImageGeneration
                  ? {
                      disabled: isGeneratingImage,
                      onClick: () => setIsImageDialogOpen(true),
                      title: "Generate image",
                    }
                  : undefined
              }
              stopAction={activeTurnId ? { onStop: () => void handleStopTurn() } : undefined}
            />
          </div>
        </div>

        {expandedCanvas && <CanvasSidePanel canvas={expandedCanvas} onClose={() => setExpandedCanvas(null)} />}
      </div>

      <EditConversationDialog
        conversation={conversation}
        agents={agents}
        open={isEditing}
        onOpenChange={setIsEditing}
        onSave={handleUpdate}
      />

      <ConfirmationDialog
        open={isDeleteDialogOpen}
        onOpenChange={setIsDeleteDialogOpen}
        title="Delete Conversation"
        description={`Are you sure you want to delete "${conversation.title}"? This action cannot be undone and all messages will be lost.`}
        confirmText="Delete Conversation"
        variant="destructive"
        loading={isDeleting}
        loadingText="Deleting..."
        onConfirm={handleDelete}
      />

      <GenerateImageDialog
        open={isImageDialogOpen}
        onOpenChange={setIsImageDialogOpen}
        generating={isGeneratingImage}
        onGenerate={(prompt) => void handleGenerateImage(prompt)}
      />

      <Dialog open={images.unavailableOpen} onOpenChange={images.setUnavailableOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Image Attachments Unavailable</DialogTitle>
            <DialogDescription>{images.unavailableMessage}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button onClick={() => images.setUnavailableOpen(false)}>OK</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function nextAnimationFrame(): Promise<void> {
  return new Promise((resolve) => requestAnimationFrame(() => resolve()));
}
