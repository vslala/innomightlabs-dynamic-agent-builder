/**
 * A bare JSON POST to the API, without auth. The adapters use it instead of the HTTP client, which depends on
 * the token port: going through the client would be a cycle.
 */

export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export class ApiRequestError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
  }
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new ApiRequestError(response.status, `${path} failed with ${response.status}`);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
