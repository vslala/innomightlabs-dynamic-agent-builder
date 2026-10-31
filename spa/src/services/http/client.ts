/**
 * HTTP Client with authentication interceptor.
 *
 * This client:
 * 1. Attaches the platform's access token and the active account to every request
 * 2. On a 401, asks the platform for a fresh token and retries once (the web has none, so it signs out)
 * 3. Redirects home when the session is gone
 */

import { platform } from "../../platform";

// The account requests act in. The API also remembers the last one used.
const ACCOUNT_HEADER = "X-Account-Id";

export function getActiveAccountId(): string | null {
  return platform().storage.get("active_account_id");
}

export function setActiveAccountId(accountId: string | null): void {
  if (accountId) {
    platform().storage.set("active_account_id", accountId);
  } else {
    platform().storage.remove("active_account_id");
  }
}

/** The headers every signed-in request carries. */
export function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const token = platform().tokens.accessToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const accountId = getActiveAccountId();
  if (accountId) {
    headers[ACCOUNT_HEADER] = accountId;
  }
  return headers;
}

/**
 * `fetch` with the signed-in headers, for the calls that can't use the client (streams, blobs, raw HTML).
 * A 401 gets one retry with a refreshed token; the response is returned either way, so callers keep their
 * own error handling.
 */
export async function authorizedFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const send = () => fetch(input, { ...init, headers: { ...headersRecord(init.headers), ...authHeaders() } });
  const response = await send();
  if (response.status !== 401) return response;
  return (await platform().tokens.refresh()) ? send() : response;
}

/** Plain-object headers keep their spelling, so a caller's `Content-Type` replaces the default one. */
function headersRecord(headers: HeadersInit | undefined): Record<string, string> {
  if (!headers) return {};
  if (headers instanceof Headers || Array.isArray(headers)) return Object.fromEntries(new Headers(headers).entries());
  return headers;
}

export interface HttpClientConfig {
  baseUrl: string;
}

export interface RequestOptions extends RequestInit {
  skipAuth?: boolean;
  redirectOnAuthError?: boolean;
}

class HttpClient {
  private baseUrl: string;

  constructor(config: HttpClientConfig) {
    this.baseUrl = config.baseUrl;
  }

  private async handleAuthError(redirectOnAuthError: boolean): Promise<void> {
    // Only the credential goes: the account choice and any invitation continuation survive a re-login.
    await platform().tokens.clear();
    if (redirectOnAuthError && window.location.pathname !== "/") {
      window.location.href = "/";
    }
  }

  async request<T>(
    endpoint: string,
    options: RequestOptions = {}
  ): Promise<T> {
    const { skipAuth = false, redirectOnAuthError = true, headers: customHeaders, ...restOptions } = options;

    const isFormData = restOptions.body instanceof FormData;
    const headers: Record<string, string> = {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...headersRecord(customHeaders),
    };

    const url = `${this.baseUrl}${endpoint}`;

    try {
      const send = () => fetch(url, {
        ...restOptions,
        headers: skipAuth ? headers : { ...headers, ...authHeaders() },
      });
      let response = await send();

      // An expired access token: refresh once and retry (native); the web has no refresh, so it signs out.
      if (response.status === 401 && !skipAuth && await platform().tokens.refresh()) {
        response = await send();
      }

      if (response.status === 401) {
        await this.handleAuthError(redirectOnAuthError);
        throw new HttpError(401, "Unauthorized - Please login again");
      }

      if (!response.ok) {
        const errorData: unknown = await response.json().catch(() => ({}));
        const detail = typeof errorData === "object" && errorData !== null && "detail" in errorData
          ? errorData.detail : undefined;
        const detailMessage = typeof detail === "object" && detail !== null && "message" in detail
          ? detail.message : undefined;
        const fallbackMessage = typeof errorData === "object" && errorData !== null && "message" in errorData
          ? errorData.message : undefined;
        const message = typeof detailMessage === "string" ? detailMessage
          : typeof detail === "string" && detail ? detail
          : typeof fallbackMessage === "string" && fallbackMessage ? fallbackMessage
          : "Request failed";
        if (response.status === 429 && typeof detailMessage === "string" && detailMessage) {
          window.dispatchEvent(
            new CustomEvent("rate-limit", {
              detail: {
                message: detailMessage,
                upgradeUrl: typeof detail === "object" && detail !== null && "upgrade_url" in detail
                  ? detail.upgrade_url : undefined,
              },
            })
          );
        }
        throw new HttpError(
          response.status,
          message,
          detail
        );
      }

      // Return empty object for 204 No Content
      if (response.status === 204) {
        return {} as T;
      }

      return response.json();
    } catch (error) {
      if (error instanceof HttpError) {
        throw error;
      }
      throw new HttpError(0, "Network error - please check your connection");
    }
  }

  async get<T>(endpoint: string, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: "GET" });
  }

  async post<T>(
    endpoint: string,
    data?: unknown,
    options?: RequestOptions
  ): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: "POST",
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  async postForm<T>(
    endpoint: string,
    formData: FormData,
    options?: RequestOptions
  ): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: "POST",
      body: formData,
    });
  }

  async put<T>(
    endpoint: string,
    data?: unknown,
    options?: RequestOptions
  ): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: "PUT",
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  async patch<T>(
    endpoint: string,
    data?: unknown,
    options?: RequestOptions
  ): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: "PATCH",
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  async delete<T>(endpoint: string, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: "DELETE" });
  }
}

export class HttpError extends Error {
  status: number;
  detail?: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "HttpError";
    this.status = status;
    this.detail = detail;
  }
}

// Create singleton instance
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export const httpClient = new HttpClient({
  baseUrl: apiBaseUrl,
});

export default httpClient;
