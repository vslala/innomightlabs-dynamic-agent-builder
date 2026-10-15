import { httpClient } from "../http/client";
import type {
  Capture,
  CaptureFilters,
  CapturePage,
  CreateLeadFormRequest,
  LeadForm,
  LeadFormFields,
  LeadSettings,
  LeadSettingsRequest,
  LeadUsage,
} from "../../types/leads";

/** /leads: the account's lead forms, statuses and captures. Agents capture through their skill, never from here. */
class LeadsApiService {
  listForms(): Promise<LeadForm[]> {
    return httpClient.get<LeadForm[]>("/leads/forms");
  }

  getForm(formId: string): Promise<LeadForm> {
    return httpClient.get<LeadForm>(`/leads/forms/${encodeURIComponent(formId)}`);
  }

  createForm(request: CreateLeadFormRequest): Promise<LeadForm> {
    return httpClient.post<LeadForm>("/leads/forms", request);
  }

  updateForm(formId: string, fields: LeadFormFields): Promise<LeadForm> {
    return httpClient.put<LeadForm>(`/leads/forms/${encodeURIComponent(formId)}`, fields);
  }

  archiveForm(formId: string): Promise<LeadForm> {
    return httpClient.post<LeadForm>(`/leads/forms/${encodeURIComponent(formId)}/archive`);
  }

  restoreForm(formId: string): Promise<LeadForm> {
    return httpClient.post<LeadForm>(`/leads/forms/${encodeURIComponent(formId)}/restore`);
  }

  async deleteForm(formId: string): Promise<void> {
    await httpClient.delete<void>(`/leads/forms/${encodeURIComponent(formId)}`);
  }

  getSettings(): Promise<LeadSettings> {
    return httpClient.get<LeadSettings>("/leads/settings");
  }

  updateSettings(request: LeadSettingsRequest): Promise<LeadSettings> {
    return httpClient.put<LeadSettings>("/leads/settings", request);
  }

  getUsage(): Promise<LeadUsage> {
    return httpClient.get<LeadUsage>("/leads/usage");
  }

  listCaptures(filters: CaptureFilters, cursor?: string | null, limit = 25): Promise<CapturePage> {
    const query = new URLSearchParams({ limit: String(limit) });
    for (const [name, value] of Object.entries(filters)) {
      if (value !== undefined && value !== "" && value !== false) query.set(name, String(value));
    }
    if (cursor) query.set("cursor", cursor);
    return httpClient.get<CapturePage>(`/leads/captures?${query.toString()}`);
  }

  getCapture(captureId: string): Promise<Capture> {
    return httpClient.get<Capture>(`/leads/captures/${encodeURIComponent(captureId)}`);
  }

  updateCaptureStatus(captureId: string, status: string): Promise<Capture> {
    return httpClient.patch<Capture>(`/leads/captures/${encodeURIComponent(captureId)}`, { status });
  }

  async deleteCapture(captureId: string): Promise<void> {
    await httpClient.delete<void>(`/leads/captures/${encodeURIComponent(captureId)}`);
  }

  /** A short-lived link that downloads the file; files are never shown inline. */
  async fileDownloadUrl(captureId: string, fileId: string): Promise<string> {
    const { url } = await httpClient.get<{ url: string }>(
      `/leads/captures/${encodeURIComponent(captureId)}/files/${encodeURIComponent(fileId)}`
    );
    return url;
  }
}

export const leadsApiService = new LeadsApiService();
