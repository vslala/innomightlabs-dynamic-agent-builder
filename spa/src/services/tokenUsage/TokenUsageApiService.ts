/**
 * Token Usage API Service - calls the analytics backend for per-agent LLM token usage.
 */

import { httpClient } from "../http/client";

export type TokenUsagePeriod = "day" | "month" | "year";

export interface TokenUsageQueryParams {
  period: TokenUsagePeriod;
  from?: string;
  to?: string;
  llm_model?: string;
}

export interface TokenUsagePoint {
  period_key: string;
  period_start: string;
  llm_model: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  call_count: number;
}

export interface TokenUsageTimeseriesResponse {
  agent_id: string;
  period: TokenUsagePeriod;
  from: string;
  to: string;
  llm_model_filter: string | null;
  series: TokenUsagePoint[];
}

function buildQuery(params: TokenUsageQueryParams): string {
  const searchParams = new URLSearchParams();
  searchParams.set("period", params.period);
  if (params.from) searchParams.set("from", params.from);
  if (params.to) searchParams.set("to", params.to);
  if (params.llm_model) searchParams.set("llm_model", params.llm_model);
  return searchParams.toString();
}

class TokenUsageApiService {
  async getTokenUsage(
    agentId: string,
    params: TokenUsageQueryParams
  ): Promise<TokenUsageTimeseriesResponse> {
    return httpClient.get<TokenUsageTimeseriesResponse>(
      `/analytics/agents/${agentId}/token-usage?${buildQuery(params)}`
    );
  }
}

// Singleton instance
export const tokenUsageApiService = new TokenUsageApiService();
