import { useEffect, useState } from "react";
import { ChevronLeft, Bot } from "lucide-react";
import { Link, Outlet, useNavigate, useParams } from "react-router-dom";

import { Button } from "../../../components/ui/button";
import { Card, CardContent } from "../../../components/ui/card";
import { agentApiService, type AgentResponse } from "../../../services/agents/AgentApiService";
import { AgentSideNav } from "./AgentSideNav";

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
      <div className="flex items-center justify-center h-64">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--gradient-start)] border-t-transparent" />
      </div>
    );
  }

  if (error || !agent) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => navigate("/dashboard/agents")}>
            <ChevronLeft className="h-5 w-5" />
          </Button>
          <h1 className="text-xl font-semibold text-[var(--text-primary)]">Agent Not Found</h1>
        </div>
        <Card>
          <CardContent className="p-12">
            <div className="text-center">
              <Bot className="h-16 w-16 mx-auto text-[var(--text-muted)] mb-4" />
              <p className="text-[var(--text-muted)] mb-6">
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
    <div style={{ display: "flex", flexDirection: "column", gap: "2rem" }}>
      <div className="flex items-center justify-between gap-6">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" asChild>
            <Link to="/dashboard/agents">
              <ChevronLeft className="h-5 w-5" />
            </Link>
          </Button>
          <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-[var(--gradient-start)] to-[var(--gradient-mid)] flex items-center justify-center">
            <Bot className="h-6 w-6 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-[var(--text-primary)]">
              {agent.agent_name}
            </h1>
            <p className="text-sm text-[var(--text-muted)]">{agent.agent_provider}</p>
          </div>
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "15rem minmax(0, 1fr)",
          gap: "2rem",
          alignItems: "start",
        }}
      >
        <AgentSideNav />
        <div style={{ minWidth: 0 }}>
          <Outlet context={{ agent }} />
        </div>
      </div>
    </div>
  );
}
