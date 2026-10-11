import { httpClient, HttpError, type RequestOptions } from "../http/client";

export type InvitationStatus = "pending" | "accepted" | "revoked" | "expired";
export interface Invitation {
  account_id: string;
  invite_id: string;
  email: string;
  invited_by: string;
  expires_at: string;
  status: InvitationStatus;
  delivery_status: "pending" | "sent" | "failed";
  accepted_by: string | null;
  created_at: string;
}
export interface InvitationPreview {
  account_id: string;
  account_name: string;
  email: string;
  expires_at: string;
  status: InvitationStatus;
  login_context: string;
}
export interface InvitationErrorDetail {
  code?: string;
  message: string;
  invite_id?: string;
}
export class InvitationError extends HttpError {
  declare detail: InvitationErrorDetail;

  constructor(status: number, detail: InvitationErrorDetail) {
    super(status, detail.message, detail);
  }
}
export function invitationErrorMessage(error: unknown): string {
  if (error instanceof InvitationError) {
    if (error.detail.code === "SEAT_LIMIT_UNAVAILABLE") return `${error.message} Please contact the account administrator to check billing and seat availability, then retry.`;
    if (error.detail.code === "SEAT_LIMIT_REACHED") return `${error.message} Ask the account administrator to free a seat or upgrade the plan.`;
  }
  return error instanceof Error ? error.message : "Please try again.";
}

async function request<T>(path: string, method: string, body?: unknown, signal?: AbortSignal, options: Pick<RequestOptions, "skipAuth" | "redirectOnAuthError"> = {}): Promise<T> {
  try {
    return await httpClient.request<T>(path, {
      method, signal, ...options,
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  } catch (error) {
    if (error instanceof HttpError) {
      const detail = error.detail;
      if (typeof detail === "object" && detail !== null && !Array.isArray(detail)) {
        throw new InvitationError(error.status, {
          message: "message" in detail && typeof detail.message === "string" ? detail.message : error.message,
          ...("code" in detail && typeof detail.code === "string" ? { code: detail.code } : {}),
          ...("invite_id" in detail && typeof detail.invite_id === "string" ? { invite_id: detail.invite_id } : {}),
        });
      }
    }
    throw error;
  }
}

export const invitationService = {
  list: (signal?: AbortSignal) => request<Invitation[]>("/iam/invitations", "GET", undefined, signal),
  create: (email: string) => request<Invitation>("/iam/invitations", "POST", { email }),
  resend: (id: string) => request<Invitation>(`/iam/invitations/${encodeURIComponent(id)}/resend`, "POST"),
  revoke: (id: string) => request<void>(`/iam/invitations/${encodeURIComponent(id)}`, "DELETE"),
  preview: (token: string, signal?: AbortSignal) => request<InvitationPreview>("/invitations/preview", "POST", { token }, signal, { skipAuth: true }),
  accept: (token: string) => request<{ account_id: string; invite_id: string }>("/invitations/accept", "POST", { token }, undefined, { redirectOnAuthError: false }),
};
