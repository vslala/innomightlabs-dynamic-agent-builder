import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Bot, Search, Sparkles } from "lucide-react";

import {
  Button,
  Card,
  CardContent,
  EmptyState,
  ErrorState,
  Input,
  LoadingState,
} from "../../../components/ui";
import { Grid, Inline, Page, PageActions, PageBody, PageDescription, PageHeader, PageTitle, Stack } from "../../../components/layout";
import { agentMarketplaceApiService } from "../../../services/agentMarketplace";
import type { MarketplaceAgentSummary } from "../../../types/agentMarketplace";

export function AgentMarketplacePage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [agents, setAgents] = useState<MarketplaceAgentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadAgents = async (nextQuery = query) => {
    try {
      setError(null);
      const data = await agentMarketplaceApiService.listAgents(nextQuery);
      setAgents(data);
    } catch (err) {
      console.error("Error loading marketplace agents:", err);
      setError("Failed to load marketplace agents.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadAgents("");
  }, []);

  const handleSearch = (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    void loadAgents(query);
  };

  return (
    <Page>
      <PageHeader>
        <Stack gap="xs">
          <PageTitle>Agent Marketplace</PageTitle>
          <PageDescription>
            Browse shared agents, inspect their instructions, and import a configured copy.
          </PageDescription>
        </Stack>
        <PageActions>
          <Button variant="outline" onClick={() => navigate("/dashboard/agents")}>
            Back to Agents
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
                placeholder="Search marketplace agents"
                style={{ paddingInlineStart: "var(--space-10)" }}
              />
            </div>
            <Button type="submit">Search</Button>
          </Inline>
        </form>

        {loading ? (
          <LoadingState />
        ) : error ? (
          <ErrorState message={error} onRetry={() => void loadAgents(query)} />
        ) : agents.length === 0 ? (
          <EmptyState
            icon={Sparkles}
            title="No marketplace agents found"
            description="Try a different search, or publish one of your own agents."
          />
        ) : (
          <Grid className="grid-cols-1 md:grid-cols-2 xl:grid-cols-3" gap="md">
            {agents.map((agent) => (
              <Card key={agent.template_id} className="transition-colors hover:border-[var(--gradient-start)]/60">
                <CardContent>
                  <Stack gap="md">
                    <Inline gap="md" align="flex-start" wrap={false}>
                      <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-[var(--gradient-start)] to-[var(--gradient-mid)]">
                        <Bot className="h-6 w-6 text-white" />
                      </div>
                      <Stack gap="xs">
                        <Link to={`/dashboard/agents/marketplace/${agent.template_id}`}>
                          <h2 className="line-clamp-2 text-base font-semibold text-[var(--text-primary)] hover:text-[var(--gradient-start)]">
                            {agent.title}
                          </h2>
                        </Link>
                        <p className="text-xs text-[var(--text-muted)]">
                          by {agent.publisher_display_name} · {agent.import_count} imports
                        </p>
                      </Stack>
                    </Inline>

                    <p className="line-clamp-3 text-sm leading-6 text-[var(--text-secondary)]">
                      {agent.short_description}
                    </p>

                    {agent.tags.length > 0 ? (
                      <Inline gap="xs">
                        {agent.tags.slice(0, 4).map((tag) => (
                          <span key={tag} className="rounded-md bg-[var(--bg-secondary)] px-2.5 py-1 text-xs text-[var(--text-muted)]">
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
                        {agent.skill_count} skills · v{agent.template_version}
                      </span>
                      <Button size="sm" onClick={() => navigate(`/dashboard/agents/marketplace/${agent.template_id}`)}>
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
