/**
 * Client for the existing /widget/* API. The app is served from the API's own
 * origin, so every call is same-origin and uses relative URLs.
 */

import { imageErrorMessage, type UploadedImage } from "../../packages/image-attachments/src";
import type { Session } from "./session";
import { readSSE } from "./sse";

/** The code an image refusal carries in `detail.code`, which `errorDetail` returns in place of its message. */
const IMAGE_UPLOAD_LIMITED = "image_upload_limited";

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
  /** Images the visitor sent; fetch `url` with the visitor's headers (`fetchImage`). */
  image_attachments?: UploadedImageInfo[];
}

export type UploadedImageInfo = Pick<UploadedImage, "image_id" | "filename" | "url">;

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
  validation?: FormInputValidation | null;
  attr?: Record<string, string> | null;
}

/** The parts of the API's validation rules the widget uses as input hints; the API enforces them. */
export interface FormInputValidation {
  format?: "email" | "phone" | "url" | "number" | "date" | null;
  max_length?: number | null;
  max_items?: number | null;
  max_file_bytes?: number | null;
  accept?: string[] | null;
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
  /** The lead form being shown, when it is one: its file fields upload against it. */
  lead_form?: string | null;
}

/** A file uploaded into a lead form; its id goes in the field's answer. */
export interface UploadedLeadFile {
  file_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
}

interface TokenResponse {
  access_token: string;
  refresh_token?: string | null;
  visitor: { visitor_id: string; email: string; kind?: "google" | "guest"; name?: string | null; picture?: string | null };
}

/** The visitor's sign-in is no longer valid; they have to sign in again. */
export class SignedOutError extends Error {}
export class GuestSessionEndedError extends SignedOutError {}

export class GuestEntryError extends Error {
  readonly retryable: boolean;
  constructor(message: string, retryable = false) {
    super(message);
    this.retryable = retryable;
  }
}

export class WidgetApi {
  private readonly publicKey: string;
  private readonly token: () => Promise<string>;

  constructor(publicKey: string, token: () => Promise<string>) {
    this.publicKey = publicKey;
    this.token = token;
  }

  static async startGuest(publicKey: string, email: string, signal?: AbortSignal): Promise<Session> {
    const response = await fetch("/widget/auth/guest", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": publicKey },
      body: JSON.stringify({ email }),
      signal,
    });
    if (!response.ok) {
      const detail = await errorDetail(response);
      if (response.status === 429) throw new GuestEntryError("Guest chat is temporarily limited. Please try again later or continue with Google.");
      if (response.status === 404) throw new GuestEntryError("Guest access is no longer available. Please continue with Google.");
      if (response.status === 422 && !/timeout|timed out|couldn't check|could not check/i.test(detail)) {
        throw new GuestEntryError(detail);
      }
      throw new GuestEntryError("We couldn't check that address. Please try again.", true);
    }
    return sessionFrom(await response.json() as TokenResponse);
  }

  async endGuest(): Promise<void> {
    await this.request("/widget/auth/guest/end", { method: "POST" });
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

  /** Upload an image to send with the visitor's next message. */
  uploadImage(conversationId: string, file: File): Promise<UploadedImage> {
    const form = new FormData();
    form.append("file", file);
    return this.json(`/widget/conversations/${encodeURIComponent(conversationId)}/images`, { method: "POST", body: form });
  }

  uploadLeadFile(conversationId: string, leadForm: string, inputName: string, file: File): Promise<UploadedLeadFile> {
    const form = new FormData();
    form.append("form", leadForm);
    form.append("input", inputName);
    form.append("file", file);
    return this.json(`/widget/conversations/${encodeURIComponent(conversationId)}/lead-files`, { method: "POST", body: form });
  }

  /** An image of the visitor's own conversation as a blob URL; the endpoint needs their headers, so an <img> can't load it. */
  async fetchImage(url: string): Promise<string> {
    // The API sends absolute URLs; the app is served from the API's own origin, so only the path is used.
    const { pathname, search } = new URL(url, globalThis.location?.href);
    const response = await this.request(pathname + search, {});
    return URL.createObjectURL(await response.blob());
  }

  async *sendMessage(
    conversationId: string,
    content: string,
    imageIds: string[],
    signal?: AbortSignal
  ): AsyncGenerator<StreamEvent> {
    const response = await this.request(`/widget/conversations/${encodeURIComponent(conversationId)}/messages`, {
      method: "POST",
      body: JSON.stringify({ content, image_ids: imageIds }),
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
        // A FormData body sets its own multipart boundary
        ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        "X-API-Key": this.publicKey,
        Authorization: `Bearer ${await this.token()}`,
        ...init.headers,
      },
    });
    if (!response.ok) await throwResponseError(response);
    return response;
  }
}

async function authPost(publicKey: string, path: string, body: object): Promise<TokenResponse> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": publicKey },
    body: JSON.stringify(body),
  });
  if (!response.ok) await throwResponseError(response);
  return (await response.json()) as TokenResponse;
}

function sessionFrom(body: TokenResponse): Session {
  return {
    token: body.access_token,
    refreshToken: body.refresh_token,
    visitor: {
      visitorId: body.visitor.visitor_id,
      kind: body.visitor.kind ?? "google",
      email: body.visitor.email,
      name: body.visitor.name,
      picture: body.visitor.picture,
    },
  };
}

async function throwResponseError(response: Response): Promise<never> {
  const detail = await errorDetail(response);
  if (response.status === 401) {
    if (detail === "guest_session_ended") throw new GuestSessionEndedError("This guest chat has ended.");
    throw new SignedOutError("Your sign-in has expired.");
  }
  if (response.status === 409 && detail === "guest_turn_in_progress") {
    throw new Error("Please wait for the reply to finish before sending another message.");
  }
  if (response.status === 429 && detail === IMAGE_UPLOAD_LIMITED) {
    throw new Error("Too many images. Try again in a moment.");
  }
  if (response.status === 429) throw new Error("Chat is temporarily limited. Please try again later. Guests can end this chat and continue with Google.");
  throw new Error(detail);
}

async function errorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    // An image the API refused: `{code, message}`. The code decides below; the message is what to show.
    if (body.detail && typeof body.detail === "object" && "code" in body.detail && body.detail.code === IMAGE_UPLOAD_LIMITED) {
      return IMAGE_UPLOAD_LIMITED;
    }
    if (body.detail && typeof body.detail === "object" && "message" in body.detail) return imageErrorMessage(body.detail);
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
