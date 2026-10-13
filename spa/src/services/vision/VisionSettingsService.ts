import { httpClient } from "../http/client";
import type { FormSchema } from "../../types/form";

export interface VisionSettings {
  enabled: boolean;
  provider_name?: string | null;
  model_name?: string | null;
  is_configured: boolean;
}

export interface VisionSettingsRequest {
  enabled: boolean;
  provider_name?: string | null;
  model_name?: string | null;
}

/** The account's image reading: whether it is on and which vision model reads images. Admins change it. */
class VisionSettingsService {
  async getSettings(): Promise<VisionSettings> {
    return httpClient.get<VisionSettings>("/vision/settings");
  }

  async getSettingsSchema(): Promise<FormSchema> {
    return httpClient.get<FormSchema>("/vision/settings/schema");
  }

  async saveSettings(data: VisionSettingsRequest): Promise<VisionSettings> {
    return httpClient.put<VisionSettings>("/vision/settings", data);
  }
}

export const visionSettingsService = new VisionSettingsService();
