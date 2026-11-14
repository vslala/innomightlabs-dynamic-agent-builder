import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { SearchInput } from "../../components/ui/search-input";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { conversationApiService } from "../../services/conversations";
import { agentApiService, type AgentResponse } from "../../services/agents/AgentApiService";
import { agentDisplayName } from "../../services/builder/ila";
import { defaultAgentService } from "../../services/settings/DefaultAgentService";
import type { ConversationKind, ConversationResponse } from "../../types/conversation";
import { userVisibleConversations } from "../../utils/conversations";
import { ConversationCloud } from "./conversations/cloud/ConversationCloud";
import { ConversationKindTabs } from "./conversations/ConversationKindTabs";
import { kindDetails, parseKind } from "./conversations/conversationKind";
import { loadView, saveView, type ConversationView } from "./conversations/conversationView";
import { ConversationSidebar } from "./conversations/ConversationSidebar";
import { ConversationViewToggle } from "./conversations/ConversationViewToggle";
import {
  ConversationStartComposer,
  type ConversationStartMode,
} from "./conversations/ConversationStartComposer";
import styles from "./Conversations.module.css";

/** Below Tailwind's lg the classic view is one column, the list above a docked composer. Keep in step with Conversations.module.css. */
const ONE_COLUMN_QUERY = "(max-width: 1023px)";

export function Conversations() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const kind = parseKind(searchParams.get("type"));
  const [conversations, setConversations] = useState<ConversationResponse[]>([]);
  const [agents, setAgents] = useState<AgentResponse[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [prompt, setPrompt] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [mode, setMode] = useState<ConversationStartMode>("chat");
  const [debugEnabled, setDebugEnabled] = useState(false);
  const [view, setView] = useState<ConversationView>(loadView);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [listLoading, setListLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const oneColumn = useMediaQuery(ONE_COLUMN_QUERY);

  const loadAgents = async () => {
    try {
      const [agentsData, defaultAgentPreference] = await Promise.all([
        agentApiService.listAgents(),
        defaultAgentService.getDefaultAgent().catch(() => null),
      ]);
      setAgents(agentsData);

      // A default agent that's been deleted/lost access is treated as unset, not an error.
      const defaultAgentId = defaultAgentPreference?.agent_id;
      const validDefaultAgentId = agentsData.some((agent) => agent.agent_id === defaultAgentId)
        ? defaultAgentId
        : null;
      setSelectedAgentId((current) => current || validDefaultAgentId || agentsData[0]?.agent_id || "");
    } catch (err) {
      setError("Failed to load conversations. Please try again.");
      console.error("Error loading agents:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadAgents();
  }, []);

  // Each tab lists its own kind from the server, so its first page is full. A tab changed mid-load drops the late answer.
  useEffect(() => {
    let current = true;
    setListLoading(true);
    setConversations([]);
    conversationApiService
      .listConversations(50, undefined, kind)
      .then((page) => {
        if (!current) return;
        setError(null);
        setConversations(kind === "chat" ? userVisibleConversations(page.items) : page.items);
      })
      .catch((err) => {
        if (!current) return;
        setError("Failed to load conversations. Please try again.");
        console.error("Error loading conversations:", err);
      })
      .finally(() => current && setListLoading(false));
    return () => {
      current = false;
    };
  }, [kind]);

  const filteredConversations = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return conversations;
    return conversations.filter((conversation) => {
      const agentName = getAgentName(agents, conversation.agent_id).toLowerCase();
      return (
        conversation.title.toLowerCase().includes(query) ||
        (conversation.description || "").toLowerCase().includes(query) ||
        agentName.includes(query)
      );
    });
  }, [agents, conversations, search]);

  const handleStartConversation = async () => {
    const message = prompt.trim();
    if (!message || !selectedAgentId || creating) return;

    setCreating(true);
    setError(null);
    try {
      const conversation = await conversationApiService.createConversation({
        title: titleFromPrompt(message, mode),
        agent_id: selectedAgentId,
      });
      setPrompt("");
      setFiles([]);
      navigate(`/dashboard/conversations/${conversation.conversation_id}`, {
        state:
          mode === "image"
            ? { initialImagePrompt: message }
            : {
                initialMessage: message,
                initialFiles: files,
                debug: debugEnabled,
              },
      });
    } catch (err) {
      setError("Failed to start conversation. Please try again.");
      console.error("Error starting conversation:", err);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (conversation: ConversationResponse) => {
    setDeletingId(conversation.conversation_id);
    try {
      await conversationApiService.deleteConversation(conversation.conversation_id);
      setConversations((items) =>
        items.filter((item) => item.conversation_id !== conversation.conversation_id)
      );
    } catch (err) {
      setError("Failed to delete conversation. Please try again.");
      console.error("Error deleting conversation:", err);
    } finally {
      setDeletingId(null);
    }
  };

  const handleNewConversation = () => {
    setPrompt("");
    setFiles([]);
    setMode("chat");
    setDebugEnabled(false);
  };

  const changeView = (next: ConversationView) => {
    setView(next);
    saveView(next);
  };
  const viewToggle = <ConversationViewToggle view={view} onChange={changeView} />;

  const changeKind = (next: ConversationKind) => {
    setSearch("");
    setSearchParams(next === "chat" ? {} : { type: next }, { replace: true });
  };
  const kindTabs = <ConversationKindTabs kind={kind} onChange={changeKind} />;
  const { noun, empty } = kindDetails(kind);
  const emptyMessage = listLoading
    ? "Loading conversations…"
    : conversations.length === 0
      ? empty
      : "No conversations match your search.";

  const composer = (
    <ConversationStartComposer
      agents={agents}
      selectedAgentId={selectedAgentId}
      prompt={prompt}
      files={files}
      mode={mode}
      debugEnabled={debugEnabled}
      creating={creating}
      error={error}
      docked={view === "cloud" || oneColumn}
      onAgentChange={(agentId) => {
        setSelectedAgentId(agentId);
        const nextAgent = agents.find((agent) => agent.agent_id === agentId);
        if (!nextAgent?.capabilities?.includes("image_generation")) {
          setMode("chat");
        }
      }}
      onPromptChange={setPrompt}
      onFilesAdded={(added) => setFiles((current) => [...current, ...added])}
      onFileRemoved={(file) => setFiles((current) => current.filter((each) => each !== file))}
      onModeChange={(nextMode) => {
        setMode(nextMode);
        if (nextMode === "image") {
          setDebugEnabled(false);
        }
      }}
      onDebugChange={setDebugEnabled}
      onSubmit={handleStartConversation}
      onCreateAgent={() => navigate("/dashboard/agents/new")}
    />
  );

  if (loading) {
    return (
      <div className={styles.loadingContainer}>
        <Loader2 className={styles.loadingSpinner} />
      </div>
    );
  }

  if (view === "classic") {
    return (
      <div className={styles.classicLayout}>
        <ConversationSidebar
          conversations={filteredConversations}
          agents={agents}
          search={search}
          deletingId={deletingId}
          viewToggle={viewToggle}
          kindTabs={kindTabs}
          emptyMessage={emptyMessage}
          onSearchChange={setSearch}
          onNewConversation={handleNewConversation}
          onDeleteConversation={handleDelete}
        />
        <main className={styles.main}>{composer}</main>
      </div>
    );
  }

  return (
    <div className={styles.layout}>
      <header className={styles.top}>
        <div className={styles.heading}>
          {kindTabs}
          <p className={styles.count}>
            {listLoading
              ? "Loading…"
              : search.trim()
                ? `${filteredConversations.length} of ${conversations.length} ${noun}`
                : `${conversations.length} ${noun}`}
          </p>
        </div>
        <div className={styles.controls}>
          {viewToggle}
          <div className={styles.search}>
            <SearchInput
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search conversations"
              aria-label="Search conversations"
            />
          </div>
        </div>
      </header>

      <ConversationCloud
        conversations={filteredConversations}
        agents={agents}
        deletingId={deletingId}
        emptyMessage={emptyMessage}
        onDelete={handleDelete}
      />

      {/* The composer stays at the bottom; the cloud takes the space above it. */}
      <div className={styles.dock}>{composer}</div>
    </div>
  );
}

function getAgentName(agents: AgentResponse[], agentId: string): string {
  return agentDisplayName(agents, agentId);
}

function titleFromPrompt(prompt: string, mode: ConversationStartMode): string {
  const normalized = prompt.replace(/\s+/g, " ").trim();
  const prefix = mode === "image" ? "Image: " : "";
  const maxLength = mode === "image" ? 53 : 60;
  if (normalized.length <= maxLength) return `${prefix}${normalized}` || "New conversation";
  return `${prefix}${normalized.slice(0, maxLength - 3).trim()}...`;
}
