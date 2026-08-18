import { useEffect, useState } from "react";
import { ChevronLeft, Bot } from "lucide-react";
import { Link, Outlet, useNavigate, useParams } from "react-router-dom";

import { Button } from "../../../components/ui/button";
import { Card, CardContent } from "../../../components/ui/card";
import { agentApiService, type AgentResponse } from "../../../services/agents/AgentApiService";
import { AgentSideNav } from "./AgentSideNav";
import "./AgentDetailLayout.css";

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
      <div className="agent-detail-layout__loading">
        <div className="agent-detail-layout__spinner" />
      </div>
    );
  }

  if (error || !agent) {
    return (
      <div className="agent-detail-layout__error">
        <div className="agent-detail-layout__error-header">
          <Button variant="ghost" size="icon" onClick={() => navigate("/dashboard/agents")}>
            <ChevronLeft className="agent-detail-layout__title-icon-svg" />
          </Button>
          <h1 className="agent-detail-layout__title">Agent Not Found</h1>
        </div>
        <Card>
          <CardContent className="agent-detail-layout__error-card">
            <div className="agent-detail-layout__error-content">
              <Bot className="agent-detail-layout__error-icon" />
              <p className="agent-detail-layout__error-message">
                {error ?? "Failed to load agent."}
              </p>
              <Button onClick={() => navigate("/dashboard/agents")}>Back to Agents</Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="agent-detail-layout">
      <div className="agent-detail-layout__header">
        <div className="agent-detail-layout__title-group">
          <Button variant="ghost" size="icon" asChild>
            <Link to="/dashboard/agents">
              <ChevronLeft className="agent-detail-layout__title-icon-svg" />
            </Link>
          </Button>
          <div className="agent-detail-layout__title-icon">
            <Bot className="agent-detail-layout__title-icon-svg" />
          </div>
          <div>
            <h1 className="agent-detail-layout__title">
              {agent.agent_name}
            </h1>
            <p className="agent-detail-layout__subtitle">{agent.agent_provider}</p>
          </div>
        </div>
      </div>

      <div className="agent-detail-layout__workspace">
        <AgentSideNav />
        <div className="agent-detail-layout__content">
          <Outlet context={{ agent }} />
        </div>
      </div>
    </div>
  );
}
