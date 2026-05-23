import { httpClient } from "../http/client";
import type { ConnectorStartRequest, ConnectorStartResponse, ConnectorStatus } from "../../types/connectors";

class ConnectorApiService {
  async listConnectors(): Promise<ConnectorStatus[]> {
    return httpClient.get<ConnectorStatus[]>("/connectors");
  }

  async startConnector(path: string, payload: ConnectorStartRequest): Promise<ConnectorStartResponse> {
    return httpClient.post<ConnectorStartResponse>(path, payload);
  }
}

export const connectorApiService = new ConnectorApiService();
