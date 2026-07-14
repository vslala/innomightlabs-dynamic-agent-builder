import { httpClient } from "../http/client";
import type {
  ImportMarketplaceAutomationRequest,
  ImportMarketplaceAutomationResponse,
  MarketplaceAutomationImportSession,
  MarketplaceAutomationDetail,
  MarketplaceAutomationImportPlan,
  MarketplaceAutomationSummary,
  PublishMarketplaceAutomationRequest,
  PublishMarketplaceAutomationResponse,
  SaveMarketplaceAutomationImportSessionRequest,
} from "../../types/automationMarketplace";

class AutomationMarketplaceApiService {
  async listAutomations(query?: string): Promise<MarketplaceAutomationSummary[]> {
    const params = query?.trim() ? `?query=${encodeURIComponent(query.trim())}` : "";
    return httpClient.get<MarketplaceAutomationSummary[]>(
      `/automation-marketplace/automations${params}`
    );
  }

  async getAutomation(templateId: string): Promise<MarketplaceAutomationDetail> {
    return httpClient.get<MarketplaceAutomationDetail>(
      `/automation-marketplace/automations/${encodeURIComponent(templateId)}`
    );
  }

  async getImportPlan(templateId: string): Promise<MarketplaceAutomationImportPlan> {
    return httpClient.get<MarketplaceAutomationImportPlan>(
      `/automation-marketplace/automations/${encodeURIComponent(templateId)}/import-plan`
    );
  }

  async importAutomation(
    templateId: string,
    payload: ImportMarketplaceAutomationRequest
  ): Promise<ImportMarketplaceAutomationResponse> {
    return httpClient.post<ImportMarketplaceAutomationResponse>(
      `/automation-marketplace/automations/${encodeURIComponent(templateId)}/import`,
      payload
    );
  }

  async saveImportSession(
    templateId: string,
    payload: SaveMarketplaceAutomationImportSessionRequest
  ): Promise<MarketplaceAutomationImportSession> {
    return httpClient.post<MarketplaceAutomationImportSession>(
      `/automation-marketplace/automations/${encodeURIComponent(templateId)}/import-session`,
      payload
    );
  }

  async publishAutomation(
    payload: PublishMarketplaceAutomationRequest
  ): Promise<PublishMarketplaceAutomationResponse> {
    return httpClient.post<PublishMarketplaceAutomationResponse>(
      "/automation-marketplace/automations/publish",
      payload
    );
  }
}

export const automationMarketplaceApiService = new AutomationMarketplaceApiService();
