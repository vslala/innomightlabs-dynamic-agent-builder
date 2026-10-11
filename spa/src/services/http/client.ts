/**
 * HTTP Client with authentication interceptor.
 *
 * This client:
 * 1. Automatically attaches Authorization header to all requests
 * 2. Intercepts responses for refreshed tokens (X-Refreshed-Token header)
 * 3. Updates localStorage with new tokens when received
 * 4. Redirects to login on authentication failures
 */

const AUTH_TOKEN_KEY = "auth_token";
const REFRESHED_TOKEN_HEADER = "x-refreshed-token";
// The account requests act in. Each tab keeps its own choice; the API also remembers the last one used.
const ACTIVE_ACCOUNT_KEY = "active_account_id";
const ACCOUNT_HEADER = "X-Account-Id";

export function getActiveAccountId(): string | null {
  return localStorage.getItem(ACTIVE_ACCOUNT_KEY);
}

export function setActiveAccountId(accountId: string | null): void {
  if (accountId) {
    localStorage.setItem(ACTIVE_ACCOUNT_KEY, accountId);
  } else {
    localStorage.removeItem(ACTIVE_ACCOUNT_KEY);
  }
}

/** The headers every signed-in request carries, for the few calls that use fetch directly (streams, blobs). */
export function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const accountId = getActiveAccountId();
  if (accountId) {
    headers[ACCOUNT_HEADER] = accountId;
  }
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

  private setAuthToken(token: string): void {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
  }

  private removeAuthToken(): void {
    localStorage.removeItem(AUTH_TOKEN_KEY);
  }

  private handleRefreshedToken(response: Response): void {
    const newToken = response.headers.get(REFRESHED_TOKEN_HEADER);
    if (newToken) {
      console.log("Received refreshed token, updating localStorage");
      this.setAuthToken(newToken);
    }
  }

  private handleAuthError(redirectOnAuthError: boolean): void {
    this.removeAuthToken();
    // Redirect to login page
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
    const headers: HeadersInit = {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...customHeaders,
    };

    if (!skipAuth) {
      Object.assign(headers, authHeaders());
    }

    const url = `${this.baseUrl}${endpoint}`;

    try {
      const response = await fetch(url, {
        ...restOptions,
        headers,
      });

      // Check for refreshed token in response headers
      this.handleRefreshedToken(response);

      // Handle authentication errors
      if (response.status === 401) {
        this.handleAuthError(redirectOnAuthError);
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
