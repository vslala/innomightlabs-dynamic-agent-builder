export interface ConnectorStatus {
  connector_id: string;
  provider_name: string;
  display_name: string;
  connected: boolean;
  connect_path: string;
  icon: string;
}

export interface ConnectorStartRequest {
  return_to: string;
}

export interface ConnectorStartResponse {
  authorize_url: string;
}
