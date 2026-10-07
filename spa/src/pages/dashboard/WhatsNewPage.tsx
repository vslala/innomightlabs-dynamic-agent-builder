import { Sparkles } from "lucide-react";
import { Card, CardContent } from "../../components/ui/card";
import { ReleaseNotes } from "../whats-new/ReleaseNotes";
import { totalChanges } from "../whats-new/whatsNewData";

export function WhatsNewPage() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <section
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1fr) auto",
          gap: "1.5rem",
          alignItems: "end",
        }}
      >
        <div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.625rem",
              marginBottom: "0.75rem",
              color: "var(--gradient-start)",
              fontSize: "0.875rem",
              fontWeight: 700,
            }}
          >
            <Sparkles className="h-4 w-4" />
            Product updates
          </div>
          <h1
            style={{
              margin: 0,
              color: "var(--text-primary)",
              fontSize: "2rem",
              lineHeight: 1.1,
              fontWeight: 800,
            }}
          >
            What's new
          </h1>
          <p
            style={{
              maxWidth: "48rem",
              marginTop: "0.75rem",
              color: "var(--text-muted)",
              fontSize: "0.95rem",
              lineHeight: 1.6,
            }}
          >
            Follow platform changes, new skills, automation improvements, and launch-stage fixes in
            one place.
          </p>
        </div>

        <Card className="hidden sm:block">
          <CardContent style={{ padding: "1rem 1.25rem" }}>
            <div style={{ color: "var(--text-muted)", fontSize: "0.75rem", fontWeight: 700 }}>
              Updates tracked
            </div>
            <div
              style={{
                marginTop: "0.25rem",
                color: "var(--text-primary)",
                fontSize: "1.75rem",
                fontWeight: 800,
              }}
            >
              {totalChanges}
            </div>
          </CardContent>
        </Card>
      </section>

      <ReleaseNotes />
    </div>
  );
}
