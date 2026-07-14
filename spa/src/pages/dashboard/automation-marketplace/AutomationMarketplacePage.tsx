import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Search, ShoppingBag, Sparkles, Workflow } from "lucide-react";

import {
  Button,
  Card,
  CardContent,
  EmptyState,
  ErrorState,
  Input,
  LoadingState,
} from "../../../components/ui";
import {
  Grid,
  Inline,
  Page,
  PageActions,
  PageBody,
  PageDescription,
  PageHeader,
  PageTitle,
  Stack,
} from "../../../components/layout";
import { automationMarketplaceApiService } from "../../../services/automationMarketplace";
import type { MarketplaceAutomationSummary } from "../../../types/automationMarketplace";

export function AutomationMarketplacePage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [automations, setAutomations] = useState<MarketplaceAutomationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadAutomations = async (nextQuery = query) => {
    try {
      setError(null);
      const data = await automationMarketplaceApiService.listAutomations(nextQuery);
      setAutomations(data);
    } catch (err) {
      console.error("Error loading marketplace automations:", err);
      setError("Failed to load marketplace automations.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadAutomations("");
  }, []);

  const handleSearch = (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    void loadAutomations(query);
  };

  return (
    <Page>
      <PageHeader>
        <Stack gap="xs">
          <PageTitle>Automation Marketplace</PageTitle>
          <PageDescription>
            Browse reusable workflow templates and import a configured private copy.
          </PageDescription>
        </Stack>
        <PageActions>
          <Button variant="outline" onClick={() => navigate("/dashboard/automations")}>
            Back to Automations
          </Button>
        </PageActions>
      </PageHeader>

      <PageBody>
        <form onSubmit={handleSearch}>
          <Inline gap="sm" wrap={false} align="stretch">
            <div className="relative min-w-0 flex-1">
              <Search className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]" />
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search marketplace automations"
                style={{ paddingInlineStart: "var(--space-10)" }}
              />
            </div>
            <Button type="submit">Search</Button>
          </Inline>
        </form>

        {loading ? (
          <LoadingState />
        ) : error ? (
          <ErrorState message={error} onRetry={() => void loadAutomations(query)} />
        ) : automations.length === 0 ? (
          <EmptyState
            icon={Sparkles}
            title="No marketplace automations found"
            description="Try a different search, or publish one of your own workflows."
          />
        ) : (
          <Grid className="grid-cols-1 md:grid-cols-2 xl:grid-cols-3" gap="md">
            {automations.map((automation) => (
              <Card
                key={automation.template_id}
                className="transition-colors hover:border-[var(--gradient-start)]/60"
              >
                <CardContent>
                  <Stack gap="md">
                    <Inline gap="md" align="flex-start" wrap={false}>
                      <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-[var(--gradient-start)] to-[var(--gradient-mid)]">
                        <Workflow className="h-6 w-6 text-white" />
                      </div>
                      <Stack gap="xs">
                        <Link to={`/dashboard/automations/marketplace/${automation.template_id}`}>
                          <h2 className="line-clamp-2 text-base font-semibold text-[var(--text-primary)] hover:text-[var(--gradient-start)]">
                            {automation.title}
                          </h2>
                        </Link>
                        <p className="text-xs text-[var(--text-muted)]">
                          by {automation.publisher_display_name} · {automation.import_count} imports
                        </p>
                      </Stack>
                    </Inline>

                    <p className="line-clamp-3 text-sm leading-6 text-[var(--text-secondary)]">
                      {automation.short_description}
                    </p>

                    {automation.tags.length > 0 ? (
                      <Inline gap="xs">
                        {automation.tags.slice(0, 4).map((tag) => (
                          <span
                            key={tag}
                            className="rounded-md bg-[var(--bg-secondary)] px-2.5 py-1 text-xs text-[var(--text-muted)]"
                          >
                            {tag}
                          </span>
                        ))}
                      </Inline>
                    ) : null}

                    <Inline
                      justify="space-between"
                      className="border-t border-[var(--border-subtle)]"
                      style={{ paddingTop: "var(--space-4)" }}
                    >
                      <span className="text-xs text-[var(--text-muted)]">
                        {automation.node_count} nodes · {automation.skill_count} skills · v
                        {automation.template_version}
                      </span>
                      <Button
                        size="sm"
                        onClick={() =>
                          navigate(`/dashboard/automations/marketplace/${automation.template_id}`)
                        }
                      >
                        <ShoppingBag className="h-4 w-4" />
                        View
                      </Button>
                    </Inline>
                  </Stack>
                </CardContent>
              </Card>
            ))}
          </Grid>
        )}
      </PageBody>
    </Page>
  );
}
