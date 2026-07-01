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
    <div className="space-y-8">
      <div className="flex items-start justify-between gap-6">
        <div>
          <h1 className="text-2xl font-semibold text-[var(--text-primary)]">Agent Marketplace</h1>
          <p className="mt-2 text-sm text-[var(--text-muted)]">
            Browse shared agents, inspect their instructions, and import a configured copy.
          </p>
        </div>
        <Button variant="outline" onClick={() => navigate("/dashboard/agents")}>
          Back to Agents
        </Button>
      </div>

      <form onSubmit={handleSearch} className="flex gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search marketplace agents"
            className="pl-10"
          />
        </div>
        <Button type="submit">Search</Button>
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
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
          {agents.map((agent) => (
            <Card key={agent.template_id} className="transition-colors hover:border-[var(--gradient-start)]/60">
              <CardContent className="space-y-5">
                <div className="flex items-start gap-4">
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-[var(--gradient-start)] to-[var(--gradient-mid)]">
                    <Bot className="h-6 w-6 text-white" />
                  </div>
                  <div className="min-w-0">
                    <Link to={`/dashboard/agents/marketplace/${agent.template_id}`}>
                      <h2 className="line-clamp-2 text-base font-semibold text-[var(--text-primary)] hover:text-[var(--gradient-start)]">
                        {agent.title}
                      </h2>
                    </Link>
                    <p className="mt-1 text-xs text-[var(--text-muted)]">
                      by {agent.publisher_display_name} · {agent.import_count} imports
                    </p>
                  </div>
                </div>

                <p className="line-clamp-3 text-sm leading-6 text-[var(--text-secondary)]">
                  {agent.short_description}
                </p>

                <div className="flex flex-wrap gap-2">
                  {agent.tags.slice(0, 4).map((tag) => (
                    <span key={tag} className="rounded-md bg-[var(--bg-secondary)] px-2.5 py-1 text-xs text-[var(--text-muted)]">
                      {tag}
                    </span>
                  ))}
                </div>

                <div className="flex items-center justify-between border-t border-[var(--border-subtle)] pt-4">
                  <span className="text-xs text-[var(--text-muted)]">{agent.skill_count} skills · v{agent.template_version}</span>
                  <Button size="sm" onClick={() => navigate(`/dashboard/agents/marketplace/${agent.template_id}`)}>
                    View
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
