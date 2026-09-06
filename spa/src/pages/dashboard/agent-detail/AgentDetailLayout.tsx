import { useEffect, useState } from "react";
import { ChevronLeft, Bot } from "lucide-react";
import { Link, Outlet, useNavigate, useParams } from "react-router-dom";

import { Button } from "../../../components/ui/button";
import { Card, CardContent } from "../../../components/ui/card";
import { agentApiService, type AgentResponse } from "../../../services/agents/AgentApiService";
import { getAgentIcon } from "../../../lib/agentIcons";
import { AgentSideNav } from "./AgentSideNav";
import styles from "./AgentDetailLayout.module.css";

export function AgentDetailLayout() {
  const { agentId } = useParams<{ agentId: string }>();
  const navigate = useNavigate();
  const [agent, setAgent] = useState<AgentResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadAgent() {
      if (!agentId) return;
      setLoading(true);
      setError(null);
      try {
        const data = await agentApiService.getAgent(agentId);
        if (!cancelled) {
          setAgent(data);
        }
      } catch (err) {
        console.error("Error loading agent:", err);
        if (!cancelled) {
          setError("Failed to load agent. It may not exist or you don't have access.");
          setAgent(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadAgent();

    return () => {
      cancelled = true;
    };
  }, [agentId]);

  if (loading) {
    return (
      <div className={styles.loading}>
        <div className={styles.spinner} />
      </div>
    );
  }

  if (error || !agent) {
    return (
      <div className={styles.error}>
        <div className={styles.errorHeader}>
          <Button variant="ghost" size="icon" onClick={() => navigate("/dashboard/agents")}>
            <ChevronLeft className={styles.titleIconSvg} />
          </Button>
          <h1 className={styles.title}>Agent Not Found</h1>
        </div>
        <Card>
          <CardContent className={styles.errorCard}>
            <div className={styles.errorContent}>
              <Bot className={styles.errorIcon} />
              <p className={styles.errorMessage}>
                {error ?? "Failed to load agent."}
              </p>
              <Button onClick={() => navigate("/dashboard/agents")}>Back to Agents</Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  const AgentIcon = getAgentIcon(agent.agent_name);

  return (
    <div className={styles.layout}>
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <Button variant="ghost" size="icon" asChild>
            <Link to="/dashboard/agents">
              <ChevronLeft className={styles.titleIconSvg} />
            </Link>
          </Button>
          <div className={styles.titleIcon}>
            <AgentIcon className={styles.titleIconSvg} />
          </div>
          <div>
            <h1 className={styles.title}>
              {agent.agent_name}
            </h1>
            <p className={styles.subtitle}>{agent.agent_provider}</p>
          </div>
        </div>
      </div>

      <div className={styles.workspace}>
        <AgentSideNav />
        <div className={styles.content}>
          <Outlet context={{ agent }} />
        </div>
      </div>
    </div>
  );
}
