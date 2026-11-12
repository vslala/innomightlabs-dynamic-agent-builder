import { httpClient } from "../http/client";
import type { FormSchema } from "../../types/form";

export interface ImageGenerationSettings {
  enabled: boolean;
  provider_name?: string | null;
  model_name?: string | null;
  is_configured: boolean;
}

export interface ImageGenerationSettingsRequest {
  enabled: boolean;
  provider_name?: string | null;
  model_name?: string | null;
}

/** The account's image generation: whether it is on and which provider and model draw. Admins change it. */
class ImageGenerationSettingsService {
  async getSettings(): Promise<ImageGenerationSettings> {
    return httpClient.get<ImageGenerationSettings>("/image-generation/settings");
  }

  async getSettingsSchema(): Promise<FormSchema> {
    return httpClient.get<FormSchema>("/image-generation/settings/schema");
  }

  async saveSettings(data: ImageGenerationSettingsRequest): Promise<ImageGenerationSettings> {
    return httpClient.put<ImageGenerationSettings>("/image-generation/settings", data);
  }
}

export const imageGenerationSettingsService = new ImageGenerationSettingsService();
