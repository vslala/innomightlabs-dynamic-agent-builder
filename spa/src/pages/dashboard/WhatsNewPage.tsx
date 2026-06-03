import { CalendarDays, CheckCircle2, Code2, Sparkles, Wrench } from "lucide-react";
import { Card, CardContent } from "../../components/ui/card";
import { Pill } from "../../components/ui/pill";
import { changeLogEntries, type ChangeCategory } from "./whatsNewData";

const categoryMeta: Record<
  ChangeCategory,
  {
    label: string;
    variant: "primary" | "success" | "info" | "warning";
    icon: typeof Sparkles;
  }
> = {
  new: { label: "New", variant: "primary", icon: Sparkles },
  improved: { label: "Improved", variant: "info", icon: Wrench },
  fixed: { label: "Fixed", variant: "success", icon: CheckCircle2 },
  developer: { label: "Developer", variant: "warning", icon: Code2 },
};

function formatReleaseDate(value: string): string {
  return new Intl.DateTimeFormat("en", {
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(new Date(`${value}T00:00:00Z`));
}

export function WhatsNewPage() {
  const totalChanges = changeLogEntries.reduce((count, entry) => count + entry.items.length, 0);

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

      <section style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        {changeLogEntries.map((entry) => (
          <Card key={`${entry.date}-${entry.title}`}>
            <CardContent
              style={{
                padding: "1.25rem",
                display: "grid",
                gridTemplateColumns: "10rem minmax(0, 1fr)",
                gap: "1.5rem",
              }}
              className="max-md:!grid-cols-1 max-md:!gap-4"
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "0.625rem",
                  color: "var(--text-muted)",
                  fontSize: "0.8125rem",
                  fontWeight: 600,
                }}
              >
                <CalendarDays className="h-4 w-4" />
                <time dateTime={entry.date}>{formatReleaseDate(entry.date)}</time>
              </div>

              <div>
                <h2
                  style={{
                    margin: 0,
                    color: "var(--text-primary)",
                    fontSize: "1.125rem",
                    fontWeight: 750,
                  }}
                >
                  {entry.title}
                </h2>
                <p
                  style={{
                    marginTop: "0.5rem",
                    marginBottom: "1rem",
                    color: "var(--text-muted)",
                    fontSize: "0.9rem",
                    lineHeight: 1.55,
                  }}
                >
                  {entry.summary}
                </p>

                <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                  {entry.items.map((item) => {
                    const meta = categoryMeta[item.category];
                    const Icon = meta.icon;
                    return (
                      <div
                        key={`${entry.date}-${item.title}`}
                        style={{
                          display: "grid",
                          gridTemplateColumns: "6.75rem minmax(0, 1fr)",
                          gap: "0.875rem",
                          alignItems: "start",
                        }}
                        className="max-sm:!grid-cols-1 max-sm:!gap-2"
                      >
                        <Pill variant={meta.variant} size="sm" style={{ width: "fit-content" }}>
                          <Icon className="mr-1 h-3 w-3" />
                          {meta.label}
                        </Pill>
                        <div>
                          <div
                            style={{
                              color: "var(--text-primary)",
                              fontSize: "0.925rem",
                              fontWeight: 700,
                            }}
                          >
                            {item.title}
                          </div>
                          <div
                            style={{
                              marginTop: "0.25rem",
                              color: "var(--text-muted)",
                              fontSize: "0.875rem",
                              lineHeight: 1.55,
                            }}
                          >
                            {item.description}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </section>
    </div>
  );
}
