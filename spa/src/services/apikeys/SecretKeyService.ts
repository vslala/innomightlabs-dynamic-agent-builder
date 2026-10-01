/**
 * Secret Keys Service - manages an agent's secret keys for the public /v1 API.
 */

import { httpClient } from "../http/client";

export interface SecretKeyResponse {
  key_id: string;
  agent_id: string;
  name: string;
  key_hint: string;
  is_active: boolean;
  created_at: string;
  last_used_at: string | null;
  request_count: number;
}

// Only the create response carries the plaintext secret.
export interface CreatedSecretKeyResponse extends SecretKeyResponse {
  secret: string;
}

export interface CreateSecretKeyRequest {
  name: string;
}

export interface UpdateSecretKeyRequest {
  name?: string;
  is_active?: boolean;
}

class SecretKeyService {
  async listSecretKeys(agentId: string): Promise<SecretKeyResponse[]> {
    return httpClient.get<SecretKeyResponse[]>(`/agents/${agentId}/secret-keys`);
  }

  async createSecretKey(
    agentId: string,
    data: CreateSecretKeyRequest
  ): Promise<CreatedSecretKeyResponse> {
    return httpClient.post<CreatedSecretKeyResponse>(`/agents/${agentId}/secret-keys`, data);
  }

  async updateSecretKey(
    agentId: string,
    keyId: string,
    data: UpdateSecretKeyRequest
  ): Promise<SecretKeyResponse> {
    return httpClient.patch<SecretKeyResponse>(`/agents/${agentId}/secret-keys/${keyId}`, data);
  }

  async deleteSecretKey(agentId: string, keyId: string): Promise<void> {
    await httpClient.delete(`/agents/${agentId}/secret-keys/${keyId}`);
  }
}

export const secretKeyService = new SecretKeyService();
