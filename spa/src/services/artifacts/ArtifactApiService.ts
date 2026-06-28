import { httpClient } from "../http/client";

export type ArtifactType = "html_report" | "image" | "file";

export interface ArtifactSource {
  skill_id?: string | null;
  agent_id?: string | null;
  automation_id?: string | null;
  automation_run_id?: string | null;
  automation_node_id?: string | null;
  conversation_id?: string | null;
  message_id?: string | null;
  metadata: Record<string, unknown>;
}

export interface ArtifactResponse {
  artifact_id: string;
  artifact_type: ArtifactType;
  title: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  source: ArtifactSource;
  created_at: string;
  url?: string | null;
  view_url?: string | null;
}

export interface ArtifactListResponse {
  items: ArtifactResponse[];
}

export interface ArtifactUrlResponse {
  url: string;
}

class ArtifactApiService {
  listArtifacts(limit = 50): Promise<ArtifactListResponse> {
    return httpClient.get<ArtifactListResponse>(`/artifacts?limit=${limit}`);
  }

  getArtifact(artifactId: string): Promise<ArtifactResponse> {
    return httpClient.get<ArtifactResponse>(`/artifacts/${encodeURIComponent(artifactId)}`);
  }

  getViewUrl(artifactId: string): Promise<ArtifactUrlResponse> {
    return httpClient.get<ArtifactUrlResponse>(`/artifacts/${encodeURIComponent(artifactId)}/view`);
  }

  getDownloadUrl(artifactId: string): Promise<ArtifactUrlResponse> {
    return httpClient.get<ArtifactUrlResponse>(`/artifacts/${encodeURIComponent(artifactId)}/download`);
  }
}

export const artifactApiService = new ArtifactApiService();
