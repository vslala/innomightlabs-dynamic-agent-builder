import { httpClient } from "../../../../services/http/client";
import type {
  AnalyticsOverviewResponse,
  AnalyticsQueryParams,
  AnalyticsTimeseriesResponse,
  TimeseriesMetric,
  TimeseriesBucket,
} from "./types";

function buildQuery(params: AnalyticsQueryParams & Partial<{ metric: TimeseriesMetric; bucket: TimeseriesBucket }>): string {
  const searchParams = new URLSearchParams();
  searchParams.set("from", params.from);
  searchParams.set("to", params.to);
  searchParams.set("tz", params.tz);
  if (params.sources && params.sources.length > 0) {
    searchParams.set("sources", params.sources.join(","));
  }
  if (params.metric) {
    searchParams.set("metric", params.metric);
  }
  if (params.bucket) {
    searchParams.set("bucket", params.bucket);
  }
  return searchParams.toString();
}

class AnalyticsApiService {
  async getOverview(
    agentId: string,
    params: AnalyticsQueryParams
  ): Promise<AnalyticsOverviewResponse> {
    return httpClient.get<AnalyticsOverviewResponse>(
      `/analytics/agents/${agentId}/overview?${buildQuery(params)}`
    );
  }

  async getTimeseries(
    agentId: string,
    params: AnalyticsQueryParams & { metric: TimeseriesMetric; bucket: TimeseriesBucket }
  ): Promise<AnalyticsTimeseriesResponse> {
    return httpClient.get<AnalyticsTimeseriesResponse>(
      `/analytics/agents/${agentId}/timeseries?${buildQuery(params)}`
    );
  }
}

export const analyticsApiService = new AnalyticsApiService();
