import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Search, Sparkles } from "lucide-react";

import { getAgentIcon } from "../../../lib/agentIcons";
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
import styles from "./AgentMarketplacePage.module.css";

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
            <div className={styles.searchWrap}>
              <Search className={styles.searchIcon} />
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
          <Grid className={styles.agentsGrid} gap="md">
            {agents.map((agent) => {
              const AgentIcon = getAgentIcon(agent.title);
              return (
              <Card key={agent.template_id} className={styles.agentCard}>
                <CardContent>
                  <Stack gap="md">
                    <Inline gap="md" align="flex-start" wrap={false}>
                      <div className={styles.agentIcon}>
                        <AgentIcon className={styles.agentIconSvg} />
                      </div>
                      <Stack gap="xs">
                        <Link to={`/dashboard/agents/marketplace/${agent.template_id}`}>
                          <h2 className={styles.agentTitle}>
                            {agent.title}
                          </h2>
                        </Link>
                        <p className={styles.agentMeta}>
                          by {agent.publisher_display_name} · {agent.import_count} imports
                        </p>
                      </Stack>
                    </Inline>

                    <p className={styles.agentDescription}>
                      {agent.short_description}
                    </p>

                    {agent.tags.length > 0 ? (
                      <Inline gap="xs">
                        {agent.tags.slice(0, 4).map((tag) => (
                          <span key={tag} className={styles.tag}>
                            {tag}
                          </span>
                        ))}
                      </Inline>
                    ) : null}

                    <Inline
                      justify="space-between"
                      className={styles.cardFooter}
                      style={{ paddingTop: "var(--space-4)" }}
                    >
                      <span className={styles.agentMeta}>
                        {agent.skill_count} skills · v{agent.template_version}
                      </span>
                      <Button size="sm" onClick={() => navigate(`/dashboard/agents/marketplace/${agent.template_id}`)}>
                        View
                      </Button>
                    </Inline>
                  </Stack>
                </CardContent>
              </Card>
              );
            })}
          </Grid>
        )}
      </PageBody>
    </Page>
  );
}
