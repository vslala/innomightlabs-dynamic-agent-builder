import { httpClient } from "../http/client";
import type { FormSchema } from "../../types/form";

export interface DreamSettings {
  user_email: string;
  enabled: boolean;
  provider_name: string | null;
  model_name: string | null;
  cron_expression: string;
  timezone: string;
  soft_sessions_per_run: number;
  soft_chunks_per_run: number;
  soft_actions_per_run: number;
  min_confidence: number;
  backfill_days: number;
}

export type DreamSettingsRequest = Omit<DreamSettings, "user_email">;
export interface DreamCursor { last_session_ended_at: string | null; sessions_dreamed: number; backfill_completed: boolean; }
export interface DreamRun { run_id: string; status: "running" | "succeeded" | "partial" | "failed" | "skipped"; mode: string; sessions_dreamed: number; sessions_remaining: number; chunks_planned: number; actions_executed: number; actions_skipped: number; prompt_tokens: number; completion_tokens: number; started_at: string; completed_at: string | null; error: string | null; }
export interface DreamActionLog { index: number; action_type: string; block_name: string; line_number: number | null; content_preview: string; reason: string; confidence: number; outcome: string; detail: string; session_ref: string; created_at: string; }

class DreamApiService {
  isAvailable() { return httpClient.get<{ enabled: boolean }>("/dream/status"); }
  getSettings() { return httpClient.get<DreamSettings | null>("/dream/settings"); }
  getSettingsSchema() { return httpClient.get<FormSchema>("/dream/settings/forms/configure"); }
  saveSettings(data: DreamSettingsRequest) { return httpClient.put<DreamSettings>("/dream/settings", data); }
  listRuns(agentId: string, limit = 20) { return httpClient.get<DreamRun[]>(`/agents/${agentId}/dream/runs?limit=${limit}`); }
  listActions(agentId: string, runId: string) { return httpClient.get<DreamActionLog[]>(`/agents/${agentId}/dream/runs/${runId}/actions`); }
  getCursor(agentId: string) { return httpClient.get<DreamCursor | null>(`/agents/${agentId}/dream/cursor`); }
  runNow(agentId: string) { return httpClient.post<{ status: string }>(`/agents/${agentId}/dream/run`, {}); }
}
export const dreamApiService = new DreamApiService();
