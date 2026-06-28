import { useEffect, useState } from "react";
import { ExternalLink, FileText, RefreshCw } from "lucide-react";
import { artifactApiService, type ArtifactResponse } from "../../services/artifacts";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { EmptyState } from "../../components/ui/empty-state";
import { LinkButton } from "../../components/ui/link-button";

export function ArtifactsPage() {
  const [artifacts, setArtifacts] = useState<ArtifactResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadArtifacts = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await artifactApiService.listArtifacts(100);
      setArtifacts(response.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load artifacts");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadArtifacts();
  }, []);

  if (loading) {
    return <p style={{ color: "var(--text-muted)" }}>Loading artifacts...</p>;
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Artifacts unavailable</CardTitle>
        </CardHeader>
        <CardContent style={{ display: "grid", gap: "1rem" }}>
          <p style={{ color: "var(--text-muted)" }}>{error}</p>
          <Button onClick={loadArtifacts} style={{ width: "fit-content" }}>
            <RefreshCw className="h-4 w-4" />
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (artifacts.length === 0) {
    return (
      <EmptyState
        icon={FileText}
        title="No artifacts yet"
        description="Generated reports and files will appear here after an agent or automation creates them."
      />
    );
  }

  return (
    <div style={{ display: "grid", gap: "1rem" }}>
      {artifacts.map((artifact) => (
        <Card key={artifact.artifact_id}>
          <CardContent
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "1rem",
              padding: "1rem",
            }}
          >
            <div style={{ minWidth: 0 }}>
              <p style={{ margin: 0, fontWeight: 600, color: "var(--text-primary)" }}>{artifact.title}</p>
              <p style={{ margin: "0.25rem 0 0", color: "var(--text-muted)", fontSize: "0.875rem" }}>
                {artifact.artifact_type.replace("_", " ")} · {formatBytes(artifact.size_bytes)} ·{" "}
                {new Date(artifact.created_at).toLocaleString()}
              </p>
            </div>
            <div style={{ display: "flex", gap: "0.5rem", flexShrink: 0 }}>
              {artifact.view_url ? (
                <LinkButton to={`/dashboard/artifacts/${artifact.artifact_id}`} variant="outline" size="sm">
                  <ExternalLink className="h-4 w-4" />
                  Open
                </LinkButton>
              ) : null}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (!bytes) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** index;
  return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
}
