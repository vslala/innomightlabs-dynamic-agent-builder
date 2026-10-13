import { useCallback, useEffect, useRef, useState } from "react";

import { SignedOutError, type AgentForm, type WidgetApi, type WidgetConversation } from "./api";
import { conversationIdsOutside, conversationScope, loadConversationId, saveConversationId } from "./session";

/** An image on a message: shown from the visitor's own file (`src`) while sending, or fetched from the API (`apiUrl`). */
export interface ChatImage {
  id: string;
  name: string;
  src?: string;
  apiUrl?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  images?: ChatImage[];
  /** Shown instead of `content` (e.g. "Submitted: Contact details" for a form answer). */
  display?: string;
  isError?: boolean;
}

/** An uploaded image going out with a message, and the local file to show it from. */
export interface SentImage {
  imageId: string;
  name: string;
  src: string;
}

export interface PendingForm {
  form: AgentForm;
  submitLabel: string;
}

const TITLE_LENGTH = 60;

function newestFirst(conversations: WidgetConversation[]): WidgetConversation[] {
  const activity = (conversation: WidgetConversation) => conversation.updated_at ?? conversation.created_at;
  return [...conversations].sort((a, b) => activity(b).localeCompare(activity(a)));
}

function titleFrom(text: string): string {
  const oneLine = text.replace(/\s+/g, " ").trim();
  return oneLine.length > TITLE_LENGTH ? `${oneLine.slice(0, TITLE_LENGTH - 1)}…` : oneLine || "New chat";
}

export interface ChatOptions {
  /** Sent once for the visitor, the first time the chat is seen, when there's no conversation to resume. */
  prompt?: string;
  /** Shown in the visitor's bubble instead of the full prompt. */
  promptLabel?: string;
  /** `false` offers the prompt as a suggestion instead of sending it automatically. Default `true`. */
  autoPrompt?: boolean;
  /** Whether the visitor can see the chat yet; an automatic prompt waits for this. */
  isVisible: boolean;
}

/** Conversations, messages and the live reply for one signed-in visitor. */
export function useChat(api: WidgetApi, publicKey: string, onSignedOut: () => void, options: ChatOptions) {
  const { prompt, promptLabel, isVisible } = options;
  const autoPrompt = options.autoPrompt !== false;
  const scope = conversationScope(prompt);
  const [conversations, setConversations] = useState<WidgetConversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState("");
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const [pendingForm, setPendingForm] = useState<PendingForm | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const promptSentRef = useRef(false);
  const pendingConversation = useRef<Promise<string> | null>(null);

  const fail = useCallback(
    (err: unknown) => {
      if (err instanceof SignedOutError) {
        onSignedOut();
        return;
      }
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
    },
    [onSignedOut]
  );

  const openConversation = useCallback(
    async (id: string) => {
      pendingConversation.current = null;
      setConversationId(id);
      saveConversationId(publicKey, scope, id);
      setPendingForm(null);
      setIsLoading(true);
      setError(null);
      try {
        const history = await api.listMessages(id);
        setMessages(
          history.map((message) => ({
            id: message.message_id,
            role: message.role,
            content: message.content,
            display: message.role === "user" && prompt && message.content === prompt ? promptLabel : undefined,
            images: message.image_attachments?.map((image) => ({ id: image.image_id, name: image.filename, apiUrl: image.url })),
          }))
        );
      } catch (err) {
        fail(err);
      } finally {
        setIsLoading(false);
      }
    },
    [api, publicKey, scope, prompt, promptLabel, fail]
  );

  const startNewChat = useCallback(() => {
    abortRef.current?.abort();
    pendingConversation.current = null;
    setConversationId(null);
    saveConversationId(publicKey, scope, null);
    setMessages([]);
    setPendingForm(null);
    setError(null);
  }, [publicKey, scope]);

  useEffect(() => {
    let cancelled = false;

    async function restore() {
      try {
        const loaded = newestFirst(await api.listConversations());
        if (cancelled) return;
        setConversations(loaded);
        // A chat with its own prompt only resumes its own thread. A plain chat falls back to the latest
        // conversation that no other chat on this site (e.g. a section's) is using.
        const remembered = loadConversationId(publicKey, scope);
        const claimed = conversationIdsOutside(publicKey, scope);
        const resume =
          loaded.find((conversation) => conversation.conversation_id === remembered) ??
          (prompt ? undefined : loaded.find((conversation) => !claimed.has(conversation.conversation_id)));
        if (resume) {
          await openConversation(resume.conversation_id);
        } else {
          setIsLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          fail(err);
          setIsLoading(false);
        }
      }
    }

    restore();
    return () => {
      cancelled = true;
      abortRef.current?.abort();
    };
  }, [api, publicKey, scope, prompt, openConversation, fail]);

  /** The conversation images are uploaded to: started now if the visitor hasn't sent anything yet. */
  const ensureConversation = useCallback(
    (title = ""): Promise<string> => {
      if (conversationId) return Promise.resolve(conversationId);
      // One creation however many images are pasted at once: they all wait on the same conversation.
      pendingConversation.current ??= api.createConversation(titleFrom(title)).then(
        (created) => {
          setConversationId(created.conversation_id);
          saveConversationId(publicKey, scope, created.conversation_id);
          setConversations((prev) => [created, ...prev]);
          return created.conversation_id;
        },
        (err: unknown) => {
          pendingConversation.current = null;
          throw err;
        }
      );
      return pendingConversation.current;
    },
    [api, conversationId, publicKey, scope]
  );

  const uploadImage = useCallback(
    async (file: File) => api.uploadImage(await ensureConversation(), file),
    [api, ensureConversation]
  );

  const send = useCallback(
    async (content: string, display?: string, images: SentImage[] = []) => {
      if (isSending || (!content.trim() && images.length === 0)) return;

      const controller = new AbortController();
      abortRef.current = controller;
      setIsSending(true);
      setError(null);
      setPendingForm(null);
      setMessages((prev) => [
        ...prev,
        {
          id: `local-${Date.now()}`,
          role: "user",
          content,
          display,
          images: images.map((image) => ({ id: image.imageId, name: image.name, src: image.src })),
        },
      ]);

      let reply = "";
      try {
        const id = await ensureConversation(display ?? content);
        if (controller.signal.aborted) return;

        const imageIds = images.map((image) => image.imageId);
        for await (const event of api.sendMessage(id, content, imageIds, controller.signal)) {
          if (event.event_type === "AGENT_RESPONSE_TO_USER") {
            reply += event.content;
            setStreaming(reply);
            setActiveTool(null);
          } else if (event.event_type === "TOOL_CALL_START") {
            setActiveTool(event.display_tool_name || event.tool_name || "a tool");
          } else if (event.event_type === "TOOL_CALL_RESULT") {
            setActiveTool(null);
          } else if (event.event_type === "UI_FORM_RENDER" && event.form) {
            setPendingForm({ form: event.form, submitLabel: event.submit_label || "Submit" });
          } else if (event.event_type === "ERROR") {
            throw new Error(event.content || "The agent couldn't reply. Please try again.");
          }
        }

        if (reply) {
          setMessages((prev) => [...prev, { id: `reply-${Date.now()}`, role: "assistant", content: reply }]);
        }
      } catch (err) {
        if (controller.signal.aborted) return;
        if (err instanceof SignedOutError) {
          onSignedOut();
          return;
        }
        if (reply) {
          setMessages((prev) => [...prev, { id: `reply-${Date.now()}`, role: "assistant", content: reply }]);
        }
        setMessages((prev) => [
          ...prev,
          {
            id: `error-${Date.now()}`,
            role: "assistant",
            content: err instanceof Error ? err.message : "The agent couldn't reply. Please try again.",
            isError: true,
          },
        ]);
      } finally {
        setIsSending(false);
        setStreaming("");
        setActiveTool(null);
      }
    },
    [api, ensureConversation, isSending, onSignedOut]
  );

  useEffect(() => {
    if (!prompt || !autoPrompt || !isVisible || isLoading || conversationId || promptSentRef.current) return;
    promptSentRef.current = true;
    send(prompt, promptLabel);
  }, [prompt, promptLabel, autoPrompt, isVisible, isLoading, conversationId, send]);

  // Offered until the visitor sends it or starts the conversation another way.
  const suggestion =
    prompt && !autoPrompt && !conversationId && !isLoading && !isSending && messages.length === 0
      ? { label: promptLabel || prompt, onSelect: () => send(prompt, promptLabel) }
      : null;

  return {
    conversations,
    conversationId,
    messages,
    streaming,
    activeTool,
    pendingForm,
    isSending,
    isLoading,
    error,
    suggestion,
    uploadImage,
    dismissError: () => setError(null),
    openConversation,
    startNewChat,
    send,
  };
}
