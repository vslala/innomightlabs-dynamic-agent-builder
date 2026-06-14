import { httpClient } from "../http/client";
import type { FormSchema } from "../../types/form";

export interface SmartSuggestionSettings {
  enabled: boolean;
  provider_name?: string | null;
  model_name?: string | null;
  is_configured: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface SmartSuggestionSettingsRequest {
  enabled: boolean;
  provider_name?: string | null;
  model_name?: string | null;
}

export interface SmartSuggestionRequest {
  suggestion_type: string;
  query: string;
  current_value?: string | null;
  context?: Record<string, unknown>;
}

export interface SmartSuggestionResponse {
  suggestion_type: string;
  value: string;
  display_text?: string | null;
  metadata?: Record<string, unknown>;
}

class SmartSuggestionService {
  async getSettings(): Promise<SmartSuggestionSettings> {
    return httpClient.get<SmartSuggestionSettings>("/smart-suggestions/settings");
  }

  async getSettingsSchema(): Promise<FormSchema> {
    return httpClient.get<FormSchema>("/smart-suggestions/settings/schema");
  }

  async saveSettings(data: SmartSuggestionSettingsRequest): Promise<SmartSuggestionSettings> {
    return httpClient.put<SmartSuggestionSettings>("/smart-suggestions/settings", data);
  }

  async suggest(data: SmartSuggestionRequest): Promise<SmartSuggestionResponse> {
    return httpClient.post<SmartSuggestionResponse>("/smart-suggestions", data);
  }
}

export const smartSuggestionService = new SmartSuggestionService();

