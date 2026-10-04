/**
 * Client for the existing /widget/* API. The app is served from the API's own
 * origin, so every call is same-origin and uses relative URLs.
 */

import type { Session } from "./session";
import { readSSE } from "./sse";

export interface WidgetConversation {
  conversation_id: string;
  title: string;
  created_at: string;
  updated_at: string | null;
  message_count: number;
}

export interface WidgetMessage {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface FormOption {
  value: string;
  label: string;
}

export interface FormInput {
  input_type: "text" | "text_area" | "password" | "select" | "choice" | "file_upload";
  name: string;
  label: string;
  value?: string | null;
  values?: string[] | null;
  options?: FormOption[] | null;
  attr?: Record<string, string> | null;
}

export interface AgentForm {
  form_name: string;
  form_inputs: FormInput[];
}

/** The subset of the agent's stream events the chat UI reacts to. */
export interface StreamEvent {
  event_type: string;
  content: string;
  message_id?: string | null;
  tool_call_id?: string | null;
  tool_name?: string | null;
  display_tool_name?: string | null;
  form?: AgentForm | null;
  submit_label?: string | null;
}

interface TokenResponse {
  access_token: string;
  refresh_token?: string | null;
  visitor: { visitor_id: string; email: string; name?: string | null; picture?: string | null };
}

/** The visitor's sign-in is no longer valid; they have to sign in again. */
export class SignedOutError extends Error {}

export class WidgetApi {
  private readonly publicKey: string;
  private readonly token: () => Promise<string>;

  constructor(publicKey: string, token: () => Promise<string>) {
    this.publicKey = publicKey;
    this.token = token;
  }

  listConversations(): Promise<WidgetConversation[]> {
    return this.json("/widget/conversations");
  }

  createConversation(title: string): Promise<WidgetConversation> {
    return this.json("/widget/conversations", { method: "POST", body: JSON.stringify({ title }) });
  }

  listMessages(conversationId: string): Promise<WidgetMessage[]> {
    return this.json(`/widget/conversations/${encodeURIComponent(conversationId)}/messages`);
  }

  async *sendMessage(conversationId: string, content: string, signal?: AbortSignal): AsyncGenerator<StreamEvent> {
    const response = await this.request(`/widget/conversations/${encodeURIComponent(conversationId)}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
      headers: { Accept: "text/event-stream" },
      signal,
    });
    if (!response.body) throw new Error("The reply stream could not be opened.");
    yield* readSSE<StreamEvent>(response.body);
  }

  /** Trade the visitor's refresh token for a fresh session. The refresh token rotates. */
  static async refresh(publicKey: string, refreshToken: string): Promise<Session> {
    return sessionFrom(await authPost(publicKey, "/widget/auth/refresh", { refresh_token: refreshToken }));
  }

  /** Trade the one-time code from the sign-in popup for a session. */
  static async redeem(publicKey: string, code: string): Promise<Session> {
    return sessionFrom(await authPost(publicKey, "/widget/auth/token", { code }));
  }

  /** Sign out on the server too, so the refresh token stops working. */
  static async revoke(publicKey: string, refreshToken: string): Promise<void> {
    await fetch("/widget/auth/revoke", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": publicKey },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  }

  private async json<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await this.request(path, init);
    return (await response.json()) as T;
  }

  private async request(path: string, init: RequestInit): Promise<Response> {
    const response = await fetch(path, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": this.publicKey,
        Authorization: `Bearer ${await this.token()}`,
        ...init.headers,
      },
    });
    if (response.status === 401) throw new SignedOutError("Your sign-in has expired.");
    if (!response.ok) throw new Error(await errorDetail(response));
    return response;
  }
}

async function authPost(publicKey: string, path: string, body: object): Promise<TokenResponse> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": publicKey },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new SignedOutError("Your sign-in has expired.");
  return (await response.json()) as TokenResponse;
}

function sessionFrom(body: TokenResponse): Session {
  return {
    token: body.access_token,
    refreshToken: body.refresh_token,
    visitor: {
      visitorId: body.visitor.visitor_id,
      email: body.visitor.email,
      name: body.visitor.name,
      picture: body.visitor.picture,
    },
  };
}

async function errorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // Not JSON; fall through to the generic message.
  }
  return `Something went wrong (${response.status}). Please try again.`;
}

/** Message the sign-in popup's last page posts back to the window that opened it. */
interface OAuthCallbackMessage {
  type: "innomight-oauth-callback";
  code: string;
}

/** Sign in with Google in a popup. Resolves with the new session, or rejects if the popup is blocked or closed. */
export function signInWithPopup(publicKey: string): Promise<Session> {
  const url = `/widget/auth/google?api_key=${encodeURIComponent(publicKey)}`;
  const popup = window.open(url, "innomight-embed-signin", "popup=1,width=480,height=640");

  return new Promise((resolve, reject) => {
    if (!popup) {
      reject(new Error("Your browser blocked the sign-in window. Allow pop-ups for this site and try again."));
      return;
    }

    const cleanup = () => {
      window.removeEventListener("message", onMessage);
      window.clearInterval(closedPoll);
    };

    const onMessage = (event: MessageEvent) => {
      // The callback page is served by the API, i.e. from this iframe's own origin.
      if (event.origin !== window.location.origin) return;
      if (event.source !== popup) return;
      const data = event.data as Partial<OAuthCallbackMessage> | null;
      if (data?.type !== "innomight-oauth-callback" || !data.code) return;
      cleanup();
      WidgetApi.redeem(publicKey, data.code).then(resolve, reject);
    };

    const closedPoll = window.setInterval(() => {
      if (popup.closed) {
        cleanup();
        reject(new Error("Sign-in was cancelled."));
      }
    }, 500);

    window.addEventListener("message", onMessage);
  });
}
