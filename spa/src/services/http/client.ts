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

export interface HttpClientConfig {
  baseUrl: string;
}

export interface RequestOptions extends RequestInit {
  skipAuth?: boolean;
}

class HttpClient {
  private baseUrl: string;

  constructor(config: HttpClientConfig) {
    this.baseUrl = config.baseUrl;
  }

  private getAuthToken(): string | null {
    return localStorage.getItem(AUTH_TOKEN_KEY);
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

  private handleAuthError(): void {
    this.removeAuthToken();
    // Redirect to login page
    if (window.location.pathname !== "/") {
      window.location.href = "/";
    }
  }

  async request<T>(
    endpoint: string,
    options: RequestOptions = {}
  ): Promise<T> {
    const { skipAuth = false, headers: customHeaders, ...restOptions } = options;

    const headers: HeadersInit = {
      "Content-Type": "application/json",
      ...customHeaders,
    };

    // Add Authorization header if not skipped and token exists
    if (!skipAuth) {
      const token = this.getAuthToken();
      if (token) {
        (headers as Record<string, string>)["Authorization"] = `Bearer ${token}`;
      }
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
        this.handleAuthError();
        throw new HttpError(401, "Unauthorized - Please login again");
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        if (response.status === 429 && errorData?.detail?.message) {
          window.dispatchEvent(
            new CustomEvent("rate-limit", {
              detail: {
                message: errorData.detail.message,
                upgradeUrl: errorData.detail.upgrade_url,
              },
            })
          );
        }
        throw new HttpError(
          response.status,
          errorData.detail || errorData.message || "Request failed"
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

  constructor(status: number, message: string) {
    super(message);
    this.name = "HttpError";
    this.status = status;
  }
}

// Create singleton instance
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export const httpClient = new HttpClient({
  baseUrl: apiBaseUrl,
});

export default httpClient;
