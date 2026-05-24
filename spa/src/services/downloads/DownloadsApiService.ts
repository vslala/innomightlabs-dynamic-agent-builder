import { httpClient } from "../http/client";
import type { PluginDownloadDetail, PluginDownloadsResponse } from "../../types/downloads";

export class DownloadsApiService {
  async listPlugins(): Promise<PluginDownloadsResponse> {
    return httpClient.get<PluginDownloadsResponse>("/downloads/plugins", { skipAuth: true });
  }

  async getPlugin(pluginId: string): Promise<PluginDownloadDetail> {
    return httpClient.get<PluginDownloadDetail>(
      `/downloads/plugins/${encodeURIComponent(pluginId)}`,
      { skipAuth: true }
    );
  }
}

export const downloadsApiService = new DownloadsApiService();
