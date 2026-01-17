/**
 * Provider Settings Service - manages user's LLM provider configurations.
 */

import { httpClient } from "../http/client";
import type { FormSchema } from "../../types/form";

/**
 * Provider schema with configuration status.
 */
export interface ProviderWithStatus {
  provider_name: string;
  form: FormSchema;
  is_configured: boolean;
}

/**
 * Provider settings response (without credentials).
 */
export interface ProviderSettingsResponse {
  provider_name: string;
  is_configured: boolean;
  created_at?: string;
  updated_at?: string;
}

class ProviderSettingsService {
  /**
   * List all supported providers with their configuration status.
   */
  async listProviders(): Promise<ProviderWithStatus[]> {
    return httpClient.get<ProviderWithStatus[]>("/settings/providers");
  }

  /**
   * Get settings for a specific provider.
   */
  async getProviderSettings(providerName: string): Promise<ProviderSettingsResponse> {
    return httpClient.get<ProviderSettingsResponse>(`/settings/providers/${providerName}`);
  }

  /**
   * Save provider credentials.
   */
  async saveProviderSettings(
    providerName: string,
    credentials: Record<string, string>
  ): Promise<ProviderSettingsResponse> {
    return httpClient.post<ProviderSettingsResponse>(
      `/settings/providers/${providerName}`,
      credentials
    );
  }

  /**
   * Delete provider configuration.
   */
  async deleteProviderSettings(providerName: string): Promise<void> {
    await httpClient.delete(`/settings/providers/${providerName}`);
  }
}

// Singleton instance
export const providerSettingsService = new ProviderSettingsService();
