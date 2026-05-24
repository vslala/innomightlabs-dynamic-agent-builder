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
    const { onEvent, onError, onComplete } = options;

    this.cancel();
    this.abortController = new AbortController();
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
        signal: this.abortController.signal,
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
    } finally {
      this.abortController = null;
    }
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

      await this.readSSEStream(response.body, onEvent);

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

  private async readSSEStream(
    body: ReadableStream<Uint8Array>,
    onEvent: SSEEventHandler
  ): Promise<void> {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();

      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            const jsonStr = line.slice(6);
            const event: SSEEvent = JSON.parse(jsonStr);
            onEvent(event);
          } catch (e) {
            console.error("Failed to parse SSE event:", e, line);
          }
        }
      }
    }
  }
}

// Singleton instance
export const chatService = new ChatService();
