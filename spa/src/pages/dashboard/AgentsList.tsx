import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Bot, LayoutGrid, List, Plus, ShoppingBag } from "lucide-react";
import { AgentIcon } from "../../components/AgentIcon";
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  LoadingState,
  ErrorState,
  EmptyState,
  AlertBanner,
  SearchInput,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Tabs,
  TabsList,
  TabsTrigger,
} from "../../components/ui";
import {
  agentApiService,
  type AgentAccess,
  type AgentAttachedCounts,
  type AgentResponse,
} from "../../services/agents/AgentApiService";
import { conversationApiService } from "../../services/conversations";
import { Page, PageActions, PageBody, PageDescription, PageHeader, Stack } from "../../components/layout";
import { useFavoriteAgents } from "../../hooks/useFavoriteAgents";
import { AgentCard } from "./AgentCard";
import {
  AGENT_SORTS,
  AGENT_TABS,
  ATTACHMENTS,
  hasAttachments,
  matchesQuery,
  recentAgents,
  sortAgents,
  timeAgo,
  type AgentSort,
} from "./agentDiscovery";
import styles from "./AgentsList.module.css";

const PAGE_SIZE = 12;
const STRIP_SIZE = 6;

function AgentPill({ agent }: { agent: AgentResponse }) {
  return (
    <Link to={`/dashboard/agents/${agent.agent_id}`} className={styles.pill}>
      <span className={styles.pillIcon}>
        <AgentIcon name={agent.agent_name} className={styles.pillIconSvg} />
      </span>
      <span>
        {agent.agent_name}
        <br />
        <span className={styles.pillMeta}>{agent.last_used_at ? timeAgo(agent.last_used_at) : "Not used yet"}</span>
      </span>
    </Link>
  );
}

export function AgentsList() {
  const navigate = useNavigate();
  const [agents, setAgents] = useState<AgentResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<AgentResponse | null>(
    null
  );
  const [isDeleting, setIsDeleting] = useState(false);
  const [startingChatWith, setStartingChatWith] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<AgentSort>("recent");
  const [density, setDensity] = useState<"grid" | "list">("grid");
  const [chosenTab, setChosenTab] = useState<AgentAccess | null>(null);
  const [attached, setAttached] = useState<Record<string, AgentAttachedCounts> | null>(null);
  const [required, setRequired] = useState<(keyof AgentAttachedCounts)[]>([]);
  const [shown, setShown] = useState(PAGE_SIZE);
  const { favorites, toggleFavorite } = useFavoriteAgents();
  const [toast, setToast] = useState<{ message: string; variant: "success" | "error" } | null>(null);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(timer);
  }, [toast]);

  const loadAgents = async () => {
    try {
      setError(null);
      const data = await agentApiService.listAgents();
      setAgents(data);
    } catch (err) {
      setError("Failed to load agents. Please try again.");
      console.error("Error loading agents:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAgents();
  }, []);

  // Slower than the list, so the page shows first and the filters switch on when this lands
  useEffect(() => {
    agentApiService.getAttachedCounts().then(setAttached, (err) => console.error("Error loading attachments:", err));
  }, []);

  const startChat = async (agent: AgentResponse) => {
    setStartingChatWith(agent.agent_id);
    try {
      const conversation = await conversationApiService.createConversation({
        title: `Chat with ${agent.agent_name}`,
        agent_id: agent.agent_id,
      });
      navigate(`/dashboard/conversations/${conversation.conversation_id}`);
    } catch (err) {
      console.error("Error starting conversation:", err);
      setToast({ message: `Couldn't start a chat with "${agent.agent_name}". Please try again.`, variant: "error" });
      setStartingChatWith(null);
    }
  };

  const handleDelete = async () => {
    if (!selectedAgent) return;
    const agentName = selectedAgent.agent_name;
    setIsDeleting(true);
    try {
      await agentApiService.deleteAgent(selectedAgent.agent_id);
      setIsDeleteDialogOpen(false);
      setSelectedAgent(null);
      setToast({ message: `"${agentName}" was deleted.`, variant: "success" });
      loadAgents();
    } catch (err) {
      console.error("Error deleting agent:", err);
      setToast({ message: `Failed to delete "${agentName}". Please try again.`, variant: "error" });
    } finally {
      setIsDeleting(false);
    }
  };

  const counts = useMemo(() => {
    const byAccess: Record<AgentAccess, number> = { owner: 0, shared: 0, admin: 0 };
    agents.forEach((agent) => byAccess[agent.access]++);
    return byAccess;
  }, [agents]);
  const tabs = AGENT_TABS.filter((tab) => counts[tab.access] > 0);
  const tab = tabs.find((t) => t.access === chosenTab)?.access ?? tabs[0]?.access;

  // A search looks through every agent you can see, so nothing hides behind a tab
  const searching = query.trim() !== "";
  const results = useMemo(
    () =>
      sortAgents(
        agents.filter(
          (agent) =>
            (searching ? matchesQuery(agent, query) : agent.access === tab) &&
            hasAttachments(attached?.[agent.agent_id], required),
        ),
        sort,
      ),
    [agents, attached, query, required, searching, sort, tab],
  );
  const favoriteAgents = agents.filter((agent) => favorites.has(agent.agent_id));
  const recent = recentAgents(agents, STRIP_SIZE);

  if (loading) {
    return <LoadingState />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={loadAgents} />;
  }

  return (
    <Page>
      <PageHeader>
        <PageDescription>Create and manage your AI agents</PageDescription>
        <PageActions>
          <Button variant="outline" onClick={() => navigate("/dashboard/agents/marketplace")} size="lg" aria-label="Marketplace">
            <ShoppingBag className="h-5 w-5" />
            <span className={styles.long}>Marketplace</span>
          </Button>
          <Button onClick={() => navigate("/dashboard/agents/new")} size="lg" aria-label="Create agent">
            <Plus className="h-5 w-5" />
            <span className={styles.long}>Create Agent</span>
          </Button>
        </PageActions>
      </PageHeader>

      <PageBody>
        {agents.length === 0 ? (
          <EmptyState
            icon={Bot}
            title="No agents yet"
            description="Create your first AI agent to get started. You can customize its persona and connect it to different LLM providers."
            actionLabel="Create Your First Agent"
            onAction={() => navigate("/dashboard/agents/new")}
          />
        ) : (
          <Stack gap="md" className={density === "list" ? styles.list : undefined}>
            <div className={styles.toolbar}>
              <SearchInput
                className={styles.search}
                aria-label="Search agents"
                placeholder="Search by name, what it does or provider…"
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                  setShown(PAGE_SIZE);
                }}
              />
              <Select value={sort} onValueChange={(value) => setSort(value as AgentSort)}>
                <SelectTrigger className={styles.sort} aria-label="Sort agents">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {AGENT_SORTS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <div className={styles.density}>
                <Button
                  variant={density === "grid" ? "secondary" : "ghost"}
                  size="icon"
                  aria-label="Card view"
                  aria-pressed={density === "grid"}
                  onClick={() => setDensity("grid")}
                >
                  <LayoutGrid className="h-4 w-4" />
                </Button>
                <Button
                  variant={density === "list" ? "secondary" : "ghost"}
                  size="icon"
                  aria-label="Compact list view"
                  aria-pressed={density === "list"}
                  onClick={() => setDensity("list")}
                >
                  <List className="h-4 w-4" />
                </Button>
              </div>
            </div>

            <div className={styles.filters} role="group" aria-label="Filter by what is attached">
              <span className={styles.filterLabel}>Has</span>
              {ATTACHMENTS.map(({ key, label, Icon }) => {
                const on = required.includes(key);
                return (
                  <Button
                    key={key}
                    size="sm"
                    variant={on ? "secondary" : "outline"}
                    className={styles.filterChip}
                    aria-pressed={on}
                    disabled={attached === null}
                    onClick={() => {
                      setRequired(on ? required.filter((k) => k !== key) : [...required, key]);
                      setShown(PAGE_SIZE);
                    }}
                  >
                    <Icon aria-hidden="true" />
                    {label}
                  </Button>
                );
              })}
              {required.length > 0 && (
                <Button size="sm" variant="ghost" className={styles.filterChip} onClick={() => setRequired([])}>
                  Clear
                </Button>
              )}
            </div>

            {tabs.length > 1 && !searching && (
              <Tabs
                value={tab}
                onValueChange={(value) => {
                  setChosenTab(value as AgentAccess);
                  setShown(PAGE_SIZE);
                }}
              >
                <TabsList className={styles.tabs}>
                  {tabs.map((t) => (
                    <TabsTrigger key={t.access} value={t.access}>
                      {t.label}
                      <span className={styles.count}>{counts[t.access]}</span>
                    </TabsTrigger>
                  ))}
                </TabsList>
              </Tabs>
            )}

            {!searching && required.length === 0 && favoriteAgents.length > 0 && (
              <section className={styles.strip} aria-label="Favorites">
                <h2 className={styles.stripTitle}>Favorites</h2>
                <div className={styles.pills}>
                  {favoriteAgents.map((agent) => (
                    <AgentPill key={agent.agent_id} agent={agent} />
                  ))}
                </div>
              </section>
            )}
            {!searching && required.length === 0 && recent.length > 0 && (
              <section className={styles.strip} aria-label="Recently used">
                <h2 className={styles.stripTitle}>Recently used</h2>
                <div className={styles.pills}>
                  {recent.map((agent) => (
                    <AgentPill key={agent.agent_id} agent={agent} />
                  ))}
                </div>
              </section>
            )}

            <p className={styles.resultCount} aria-live="polite">
              {searching
                ? `${results.length} result${results.length === 1 ? "" : "s"} across all agents you can see`
                : `${results.length} agent${results.length === 1 ? "" : "s"}`}
            </p>
            {results.length === 0 ? (
              <EmptyState icon={Bot} title="No agents match" description="Try fewer words, or browse the Marketplace." />
            ) : (
              <div className={styles.agentsGrid}>
                {results.slice(0, shown).map((agent) => (
                  <AgentCard
                    key={agent.agent_id}
                    agent={agent}
                    attached={attached?.[agent.agent_id]}
                    favorite={favorites.has(agent.agent_id)}
                    starting={startingChatWith === agent.agent_id}
                    onChat={startChat}
                    onToggleFavorite={toggleFavorite}
                    onDelete={(target) => {
                      setSelectedAgent(target);
                      setIsDeleteDialogOpen(true);
                    }}
                  />
                ))}
              </div>
            )}
            {results.length > shown && (
              <Button variant="outline" className={styles.more} onClick={() => setShown(shown + PAGE_SIZE)}>
                Show more ({results.length - shown} left)
              </Button>
            )}
          </Stack>
        )}
      </PageBody>

      <Dialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Agent</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete "{selectedAgent?.agent_name}"?
              This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsDeleteDialogOpen(false)}
              disabled={isDeleting}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={isDeleting}
            >
              {isDeleting ? "Deleting..." : "Delete Agent"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {toast && (
        <AlertBanner
          className={styles.toast}
          message={toast.message}
          variant={toast.variant}
          onDismiss={() => setToast(null)}
        />
      )}
    </Page>
  );
}
