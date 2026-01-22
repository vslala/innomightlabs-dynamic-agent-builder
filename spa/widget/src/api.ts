/**
 * API client for widget backend communication.
 */

import { Conversation, Message, SSEEvent } from './types';
import { getVisitorToken } from './storage';

const DEFAULT_API_URL = 'https://api.innomightlabs.com';

let apiUrl = DEFAULT_API_URL;
let apiKey = '';

/**
 * Configure the API client.
 */
export function configureApi(url: string, key: string): void {
  apiUrl = url;
  apiKey = key;
}

/**
 * Get headers for API requests.
 */
function getHeaders(includeAuth = true): HeadersInit {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    'X-API-Key': apiKey,
  };

  if (includeAuth) {
    const token = getVisitorToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
  }

  return headers;
}

/**
 * Fetch widget configuration.
 */
export async function fetchConfig(): Promise<{ agentName: string; agentId: string }> {
  const response = await fetch(`${apiUrl}/widget/config`, {
    headers: getHeaders(false),
  });

  if (!response.ok) {
    throw new Error('Failed to fetch widget config');
  }

  const data = await response.json();
  return {
    agentName: data.agent_name,
    agentId: data.agent_id,
  };
}

/**
 * Get the OAuth URL for visitor login.
 */
export function getOAuthUrl(redirectUri: string): string {
  const params = new URLSearchParams({
    api_key: apiKey,
    redirect_uri: redirectUri,
  });
  return `${apiUrl}/widget/auth/google?${params.toString()}`;
}

/**
 * Create a new conversation.
 */
export async function createConversation(title?: string): Promise<Conversation> {
  const response = await fetch(`${apiUrl}/widget/conversations`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ title }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to create conversation' }));
    throw new Error(error.detail || 'Failed to create conversation');
  }

  const data = await response.json();
  return {
    conversationId: data.conversation_id,
    agentId: data.agent_id,
    visitorId: data.visitor_id,
    visitorName: data.visitor_name,
    title: data.title,
    createdAt: data.created_at,
    updatedAt: data.updated_at,
    messageCount: data.message_count,
  };
}

/**
 * List visitor's conversations.
 */
export async function listConversations(): Promise<Conversation[]> {
  const response = await fetch(`${apiUrl}/widget/conversations`, {
    headers: getHeaders(),
  });

  if (!response.ok) {
    throw new Error('Failed to list conversations');
  }

  const data = await response.json();
  return data.map((item: Record<string, unknown>) => ({
    conversationId: item.conversation_id,
    agentId: item.agent_id,
    visitorId: item.visitor_id,
    visitorName: item.visitor_name,
    title: item.title,
    createdAt: item.created_at,
    updatedAt: item.updated_at,
    messageCount: item.message_count,
  }));
}

/**
 * List messages for a conversation.
 */
export async function listMessages(conversationId: string): Promise<Message[]> {
  const response = await fetch(`${apiUrl}/widget/conversations/${conversationId}/messages`, {
    headers: getHeaders(),
  });

  if (!response.ok) {
    throw new Error('Failed to list messages');
  }

  const data = await response.json();
  return data.map((item: Record<string, unknown>) => ({
    id: String(item.message_id),
    role: item.role as Message['role'],
    content: String(item.content),
    timestamp: new Date(String(item.created_at)),
  }));
}

/**
 * Send a message and receive streaming response.
 * Returns an async generator that yields SSE events.
 */
export async function* sendMessage(
  conversationId: string,
  content: string
): AsyncGenerator<SSEEvent, void, unknown> {
  const response = await fetch(`${apiUrl}/widget/conversations/${conversationId}/messages`, {
    method: 'POST',
    headers: {
      ...getHeaders(),
      'Accept': 'text/event-stream',
    },
    body: JSON.stringify({ content }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to send message' }));
    throw new Error(error.detail || 'Failed to send message');
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('No response body');
  }

  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') {
            return;
          }
          try {
            const event: SSEEvent = JSON.parse(data);
            yield event;
          } catch {
            // Skip invalid JSON
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
