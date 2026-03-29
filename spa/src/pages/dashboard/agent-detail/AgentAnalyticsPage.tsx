import { BarChart3 } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { useAgentDetailContext } from "./types";

export function AgentAnalyticsPage() {
  const { agent } = useAgentDetailContext();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Analytics</CardTitle>
      </CardHeader>
      <CardContent>
        <div style={{ textAlign: "center", padding: "3rem 1rem", color: "var(--text-muted)" }}>
          <BarChart3 style={{ height: "3rem", width: "3rem", margin: "0 auto 1rem", opacity: 0.5 }} />
          <p style={{ color: "var(--text-primary)", marginBottom: "0.5rem", fontWeight: 500 }}>
            Analytics is ready for this agent
          </p>
          <p style={{ fontSize: "0.875rem" }}>
            The isolated analytics grid for <strong>{agent.agent_name}</strong> will live here in the next phase.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
