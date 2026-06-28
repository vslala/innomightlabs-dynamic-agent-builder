import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { ExternalLink, FileWarning, RefreshCw } from "lucide-react";
import { artifactApiService, type ArtifactResponse } from "../../services/artifacts";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { LinkButton } from "../../components/ui/link-button";

export function ArtifactOpenPage() {
  const { artifactId } = useParams<{ artifactId: string }>();
  const [artifact, setArtifact] = useState<ArtifactResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [opening, setOpening] = useState(true);

  const openArtifact = async () => {
    if (!artifactId) {
      setError("Artifact id is missing.");
      setOpening(false);
      return;
    }

    setError(null);
    setOpening(true);
    try {
      const [artifactResponse, urlResponse] = await Promise.all([
        artifactApiService.getArtifact(artifactId),
        artifactApiService.getViewUrl(artifactId),
      ]);
      setArtifact(artifactResponse);
      window.location.replace(urlResponse.url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to open artifact");
      setOpening(false);
    }
  };

  useEffect(() => {
    void openArtifact();
  }, [artifactId]);

  if (opening) {
    return (
      <Card>
        <CardContent style={{ padding: "2rem", color: "var(--text-muted)" }}>
          Opening report...
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <FileWarning className="h-5 w-5" />
          Report unavailable
        </CardTitle>
      </CardHeader>
      <CardContent style={{ display: "grid", gap: "1rem" }}>
        <p style={{ color: "var(--text-muted)" }}>
          {error || "The report could not be opened."}
        </p>
        {artifact ? (
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>{artifact.title}</p>
        ) : null}
        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
          <Button onClick={openArtifact}>
            <RefreshCw className="h-4 w-4" />
            Try again
          </Button>
          <LinkButton to="/dashboard/artifacts" variant="outline">
            <ExternalLink className="h-4 w-4" />
            View artifacts
          </LinkButton>
        </div>
      </CardContent>
    </Card>
  );
}
