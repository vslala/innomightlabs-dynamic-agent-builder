/**
 * API Keys Service - calls backend REST API for API key management.
 */

import { httpClient } from "../http/client";

// API Key response from backend
export interface ApiKeyResponse {
  key_id: string;
  agent_id: string;
  public_key: string;
  name: string;
  allowed_origins: string[];
  is_active: boolean;
  created_at: string;
  last_used_at: string | null;
  request_count: number;
}

// Request to create a new API key
export interface CreateApiKeyRequest {
  name: string;
  allowed_origins?: string[];
}

// Request to update an API key
export interface UpdateApiKeyRequest {
  name?: string;
  allowed_origins?: string[];
  is_active?: boolean;
}

class ApiKeyService {
  /**
   * List all API keys for an agent
   */
  async listApiKeys(agentId: string): Promise<ApiKeyResponse[]> {
    return httpClient.get<ApiKeyResponse[]>(
      `/agents/${agentId}/api-keys`
    );
  }

  /**
   * Create a new API key for an agent
   */
  async createApiKey(
    agentId: string,
    data: CreateApiKeyRequest
  ): Promise<ApiKeyResponse> {
    return httpClient.post<ApiKeyResponse>(
      `/agents/${agentId}/api-keys`,
      data
    );
  }

  /**
   * Update an API key
   */
  async updateApiKey(
    agentId: string,
    keyId: string,
    data: UpdateApiKeyRequest
  ): Promise<ApiKeyResponse> {
    return httpClient.patch<ApiKeyResponse>(
      `/agents/${agentId}/api-keys/${keyId}`,
      data
    );
  }

  /**
   * Delete (revoke) an API key
   */
  async deleteApiKey(agentId: string, keyId: string): Promise<void> {
    await httpClient.delete(`/agents/${agentId}/api-keys/${keyId}`);
  }
}

// Singleton instance
export const apiKeyService = new ApiKeyService();
