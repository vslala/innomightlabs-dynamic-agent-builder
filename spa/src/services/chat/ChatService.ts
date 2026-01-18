/**
 * Chat Service - handles SSE streaming for agent conversations.
 */

import type { SSEEvent, Attachment } from "../../types/message";

const AUTH_TOKEN_KEY = "auth_token";

export type SSEEventHandler = (event: SSEEvent) => void;

export interface ChatStreamOptions {
  onEvent: SSEEventHandler;
  onError?: (error: Error) => void;
  onComplete?: () => void;
}

class ChatService {
  private baseUrl: string;
  private abortController: AbortController | null = null;

  constructor() {
    this.baseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
  }

  private getAuthToken(): string | null {
    return localStorage.getItem(AUTH_TOKEN_KEY);
  }

  /**
   * Send a message to an agent and stream the response via SSE.
   *
   * @param agentId - The agent to send the message to
   * @param conversationId - The conversation context
   * @param content - The message text content
   * @param attachments - Optional file attachments to include
   * @param options - Stream event handlers
   */
  async sendMessage(
    agentId: string,
    conversationId: string,
    content: string,
    attachments: Attachment[] | undefined,
    options: ChatStreamOptions
  ): Promise<void> {
    const { onEvent, onError, onComplete } = options;

    // Cancel any existing stream
    this.cancel();

    this.abortController = new AbortController();
    const token = this.getAuthToken();

    const url = `${this.baseUrl}/agents/${agentId}/${conversationId}/send-message`;

    // Build request body with optional attachments
    const body: { content: string; attachments?: Attachment[] } = { content };
    if (attachments && attachments.length > 0) {
      body.attachments = attachments;
    }

    try {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(body),
        signal: this.abortController.signal,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }

      if (!response.body) {
        throw new Error("No response body");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();

        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });

        // Process complete SSE messages (lines ending with double newline)
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || ""; // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const jsonStr = line.slice(6); // Remove "data: " prefix
              const event: SSEEvent = JSON.parse(jsonStr);
              onEvent(event);
            } catch (e) {
              console.error("Failed to parse SSE event:", e, line);
            }
          }
        }
      }

      onComplete?.();
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        // Stream was cancelled, don't treat as error
        return;
      }
      onError?.(error instanceof Error ? error : new Error(String(error)));
    } finally {
      this.abortController = null;
    }
  }

  /**
   * Cancel the current streaming request.
   */
  cancel(): void {
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
  }
}

// Singleton instance
export const chatService = new ChatService();
