/**
 * Chat Service - handles SSE streaming for agent conversations.
 */

import type {
  Attachment,
  GenerateImageRequest,
  GenerateImageResponse,
  SSEEvent,
} from "../../types/message";

const AUTH_TOKEN_KEY = "auth_token";
const TURN_ID_HEADER = "X-Turn-Id";
const FOLLOW_TURN_MAX_ATTEMPTS = 3;
const FOLLOW_TURN_RETRY_DELAY_MS = 500;

export type SSEEventHandler = (event: SSEEvent) => void;

export interface ChatStreamOptions {
  onEvent: SSEEventHandler;
  onError?: (error: Error) => void;
  onComplete?: () => void;
  /** Fired once the response headers arrive, before any SSE event. */
  onTurnStarted?: (turnId: string) => void;
  /** A turn is already running for this conversation; attach to it instead of erroring. */
  onConflict?: (turnId: string) => void;
  /** Aborts reading the stream. Never aborts the server-side turn itself. */
  signal?: AbortSignal;
}

/** A chat turn still running (or just finished) server-side, for reattaching after navigation. */
export interface ActiveTurn {
  turn_id: string;
  conversation_id: string;
  agent_id: string;
  status: "running" | "succeeded" | "failed" | "cancelled";
  created_at: string;
}

class ChatService {
  private baseUrl: string;

  constructor() {
    this.baseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
  }

  private getAuthToken(): string | null {
    return localStorage.getItem(AUTH_TOKEN_KEY);
  }

  async generateImage(
    agentId: string,
    conversationId: string,
    request: GenerateImageRequest
  ): Promise<GenerateImageResponse> {
    const token = this.getAuthToken();
    const url = `${this.baseUrl}/agents/${agentId}/${conversationId}/generate-image`;

    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  async generateImageStream(
    agentId: string,
    conversationId: string,
    request: GenerateImageRequest,
    options: ChatStreamOptions
  ): Promise<void> {
    const { onEvent, onError, onComplete, signal } = options;

    const token = this.getAuthToken();
    const url = `${this.baseUrl}/agents/${agentId}/${conversationId}/generate-image-stream`;

    try {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(request),
        signal,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }

      if (!response.body) {
        throw new Error("No response body");
      }

      await this.readSSEStream(response.body, onEvent);
      onComplete?.();
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        return;
      }
      onError?.(error instanceof Error ? error : new Error(String(error)));
    }
  }

  /**
   * Send a message to an agent and stream the response via SSE.
   *
   * The turn keeps running server-side even if `options.signal` later aborts
   * this read — see api/docs/LLD-async-chat-turns.md. The response carries an
   * `X-Turn-Id` header (delivered via `onTurnStarted`); a caller that wants to
   * reattach after navigating away or refreshing uses `followTurn` with that id
   * instead of resending the message.
   *
   * @param agentId - The agent to send the message to
   * @param conversationId - The conversation context
   * @param content - The message text content
   * @param attachments - Optional file attachments to include
   * @param deepResearch - Whether to enable gated research workspace tools
   * @param options - Stream event handlers
   */
  async sendMessage(
    agentId: string,
    conversationId: string,
    content: string,
    attachments: Attachment[] | undefined,
    deepResearch: boolean,
    options: ChatStreamOptions
  ): Promise<void> {
    const { onEvent, onError, onComplete, onTurnStarted, onConflict, signal } = options;
    const token = this.getAuthToken();

    const url = `${this.baseUrl}/agents/${agentId}/${conversationId}/send-message`;

    // Build request body with optional attachments
    const body: { content: string; attachments?: Attachment[]; deep_research?: boolean } = {
      content,
    };
    if (attachments && attachments.length > 0) {
      body.attachments = attachments;
    }
    if (deepResearch) {
      body.deep_research = true;
    }

    try {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(body),
        signal,
      });

      if (response.status === 409) {
        const errorData = await response.json().catch(() => ({}));
        const runningTurnId = errorData.detail?.turn_id;
        if (runningTurnId && onConflict) {
          onConflict(runningTurnId);
          return;
        }
        throw new Error(errorData.detail?.message || "This conversation already has a response in progress.");
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }

      if (!response.body) {
        throw new Error("No response body");
      }

      const turnId = response.headers.get(TURN_ID_HEADER);
      if (turnId) {
        onTurnStarted?.(turnId);
      }

      await this.readSSEStream(response.body, onEvent);

      onComplete?.();
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        // Stream was cancelled, don't treat as error
        return;
      }
      onError?.(error instanceof Error ? error : new Error(String(error)));
    }
  }

  /** The turn still running for this conversation, if any — for reattaching on mount. */
  async getActiveTurn(agentId: string, conversationId: string): Promise<ActiveTurn | null> {
    const token = this.getAuthToken();
    const response = await fetch(`${this.baseUrl}/agents/${agentId}/${conversationId}/turns/active`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return response.json();
  }

  /**
   * Tail a turn's transcript: replay everything already produced, then follow
   * live. `onComplete` fires both when the turn finishes and when the turn is
   * too old to replay (410 Gone) — in the latter case the caller should simply
   * refetch messages, since the assistant message is already persisted by then.
   */
  async followTurn(
    agentId: string,
    conversationId: string,
    turnId: string,
    options: ChatStreamOptions
  ): Promise<void> {
    const { onEvent, onError, onComplete, signal } = options;
    const token = this.getAuthToken();
    let afterSequence = 0;

    for (let attempt = 1; attempt <= FOLLOW_TURN_MAX_ATTEMPTS; attempt++) {
      const url = `${this.baseUrl}/agents/${agentId}/${conversationId}/turns/${turnId}/events?after_sequence=${afterSequence}`;

      try {
        const response = await fetch(url, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          signal,
        });

        if (response.status === 410) {
          onComplete?.();
          return;
        }
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.detail || `HTTP ${response.status}`);
        }
        if (!response.body) {
          throw new Error("No response body");
        }

        afterSequence = await this.readSSEStream(response.body, onEvent);
        onComplete?.();
        return;
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") {
          return;
        }
        if (attempt === FOLLOW_TURN_MAX_ATTEMPTS) {
          onError?.(error instanceof Error ? error : new Error(String(error)));
          return;
        }
        await sleep(FOLLOW_TURN_RETRY_DELAY_MS * attempt);
      }
    }
  }

  /** Stop an in-progress turn. A 404 means it already finished — not an error. */
  async stopTurn(agentId: string, conversationId: string, turnId: string): Promise<void> {
    const token = this.getAuthToken();
    const response = await fetch(
      `${this.baseUrl}/agents/${agentId}/${conversationId}/turns/${turnId}/stop`,
      {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      }
    );

    if (!response.ok && response.status !== 404) {
      throw new Error(`HTTP ${response.status}`);
    }
  }

  /** Reads one SSE response body, dispatching each event; returns the last `id:` sequence seen. */
  private async readSSEStream(
    body: ReadableStream<Uint8Array>,
    onEvent: SSEEventHandler
  ): Promise<number> {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let lastSequence = 0;

    const consumeBlock = (block: string) => {
      for (const line of block.split("\n")) {
        if (line.startsWith("id: ")) {
          lastSequence = Number(line.slice(4)) || lastSequence;
        } else if (line.startsWith("data: ")) {
          try {
            const jsonStr = line.slice(6);
            const event: SSEEvent = JSON.parse(jsonStr);
            onEvent(event);
          } catch (e) {
            console.error("Failed to parse SSE event:", e, line);
          }
        }
      }
    };

    while (true) {
      const { done, value } = await reader.read();

      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });

      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() || "";

      for (const block of blocks) {
        consumeBlock(block);
      }
    }

    // The stream can end (server closes the connection right after its last
    // write) before the final event's trailing blank-line separator arrives
    // as its own chunk. A well-formed final block is still parseable on its
    // own, so consume whatever is left instead of silently discarding it --
    // this is the one gap that let the turn's last event (often
    // ASSISTANT_MESSAGE_SAVED) vanish from the live view while remaining
    // correctly persisted server-side.
    if (buffer.trim()) {
      consumeBlock(buffer);
    }

    return lastSequence;
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Singleton instance
export const chatService = new ChatService();
