/**
 * Provider Settings Service - the account's LLM provider configurations, which its admins manage.
 */

import { httpClient } from "../http/client";
import type { FormSchema } from "../../types/form";

/**
 * A provider an admin signs into instead of pasting a key: a button opens `start_path`'s authorize URL, the guide
 * says what to do there, and the form (posted to its own `submit_path`) takes the pasted callback.
 */
export interface OAuthSignIn {
  start_path: string;
  button_label: string;
  guide: string;
  submit_label: string;
}

/**
 * Provider schema with configuration status.
 */
export interface ProviderWithStatus {
  provider_name: string;
  /** What Settings calls it, e.g. "OpenAI (API key)". */
  title: string;
  form: FormSchema;
  oauth: OAuthSignIn | null;
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

export interface OAuthStartResponse {
  authorize_url: string;
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
   * Save what the provider's form asks for (a key, or a pasted sign-in callback) where the form says.
   */
  async saveProviderForm(provider: ProviderWithStatus, values: Record<string, string>): Promise<ProviderSettingsResponse> {
    return httpClient.post<ProviderSettingsResponse>(provider.form.submit_path, values);
  }

  /**
   * Delete provider configuration.
   */
  async deleteProviderSettings(providerName: string): Promise<void> {
    await httpClient.delete(`/settings/providers/${providerName}`);
  }

  async startSignIn(oauth: OAuthSignIn): Promise<OAuthStartResponse> {
    return httpClient.post<OAuthStartResponse>(oauth.start_path, {});
  }
}

// Singleton instance
export const providerSettingsService = new ProviderSettingsService();
