import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ChevronRight, Hammer, MessageSquare, Package } from "lucide-react";
import { SchemaForm } from "../../../components/forms";
import {
  Alert,
  AlertDescription,
  Panel,
  PanelBody,
  PanelHeader,
  PanelTitle,
  StatusBadge,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../../../components/ui";
import { builderApiService, type BuilderSession } from "../../../services/builder/BuilderApiService";
import { kitApiService, type KitSummary } from "../../../services/kits/KitApiService";
import type { FormSchema, FormValue } from "../../../types/form";
import { kitContents, kitStatus } from "./kitView";
import styles from "./BuildPage.module.css";

export function BuildPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState<FormSchema | null>(null);
  const [sessions, setSessions] = useState<BuilderSession[]>([]);
  const [kits, setKits] = useState<KitSummary[] | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    builderApiService.getSessionForm().then(setForm).catch((err) => {
      console.error("Error loading the build form:", err);
      setError("Couldn't load the build form. Please try again.");
    });
    builderApiService.listSessions().then(setSessions).catch((err) => console.error("Error loading builds:", err));
    kitApiService.listKits().then(setKits).catch((err) => {
      console.error("Error loading kits:", err);
      setKits([]);
    });
  }, []);

  const handleStart = async (values: Record<string, FormValue>) => {
    const provider = typeof values.agent_provider === "string" ? values.agent_provider : "";
    const model = typeof values.agent_model === "string" ? values.agent_model : "";
    setStarting(true);
    setError(null);
    try {
      const session = await builderApiService.createSession(provider, model);
      navigate(`/dashboard/conversations/${session.conversation_id}`);
    } catch (err) {
      console.error("Error starting a build:", err);
      setError(err instanceof Error ? err.message : "Couldn't start building. Please try again.");
      setStarting(false);
    }
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <Hammer className={styles.headerIcon} aria-hidden="true" />
        <div>
          <h2 className={styles.title}>Build with Ada</h2>
          <p className={styles.subtitle}>
            Tell Ada what you need, and she'll set it up for you: an agent for your website, a knowledge base from
            your site, a chat widget. She shows you the plan and builds only when you approve it.
          </p>
        </div>
      </header>

      {error && (
        <Alert variant="error">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className={styles.columns}>
        <Panel>
          <PanelHeader>
            <PanelTitle>Start a new build</PanelTitle>
          </PanelHeader>
          <PanelBody className={styles.stack}>
            <p className={styles.note}>
              Ada runs on one of your providers, like your own agents do. Choose the model she should think with.
            </p>
            {form && (
              <SchemaForm
                schema={form}
                onSubmit={handleStart}
                submitLabel={starting ? "Starting…" : "Start building"}
                isLoading={starting}
              />
            )}
          </PanelBody>
        </Panel>

        <Panel>
          <Tabs defaultValue="kits">
            <PanelHeader className={styles.tabsHeader}>
              <PanelTitle>Your builds</PanelTitle>
              <TabsList>
                <TabsTrigger value="kits">Kits{kits && kits.length > 0 ? ` (${kits.length})` : ""}</TabsTrigger>
                <TabsTrigger value="conversations">Conversations</TabsTrigger>
              </TabsList>
            </PanelHeader>
            <PanelBody>
              <TabsContent value="kits">
                {kits === null ? null : kits.length === 0 ? (
                  <p className={styles.note}>
                    No kits yet. Everything Ada builds for you becomes a kit: its agents, knowledge bases and widgets,
                    kept together so you can change, roll back or remove them as one.
                  </p>
                ) : (
                  <ul className={styles.sessions}>
                    {kits.map((kit) => {
                      const status = kitStatus(kit);
                      return (
                        <li key={kit.kit_id}>
                          <Link to={`/dashboard/build/kits/${kit.kit_id}`} className={styles.kit}>
                            <Package className={styles.sessionIcon} aria-hidden="true" />
                            <span className={styles.kitText}>
                              <span className={styles.kitTitle}>{kit.title}</span>
                              <span className={styles.sessionMeta}>{kitContents(kit.counts)}</span>
                            </span>
                            <StatusBadge size="sm" status={status.status} label={status.label} />
                            <ChevronRight className={styles.sessionIcon} aria-hidden="true" />
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </TabsContent>
              <TabsContent value="conversations">
                {sessions.length === 0 ? (
                  <p className={styles.note}>Nothing yet. Your conversations with Ada will appear here.</p>
                ) : (
                  <ul className={styles.sessions}>
                    {sessions.map((session) => (
                      <li key={session.conversation_id}>
                        <Link to={`/dashboard/conversations/${session.conversation_id}`} className={styles.session}>
                          <MessageSquare className={styles.sessionIcon} aria-hidden="true" />
                          <span>{new Date(session.created_at).toLocaleString()}</span>
                          <span className={styles.sessionMeta}>
                            {session.kit_id ? "Built" : "In progress"} · {session.provider}
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </TabsContent>
            </PanelBody>
          </Tabs>
        </Panel>
      </div>
    </div>
  );
}
