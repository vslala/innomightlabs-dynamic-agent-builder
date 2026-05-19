import { useCallback, useEffect, useState } from "react";
import { ChevronLeft, Workflow } from "lucide-react";
import { Link, Outlet, useNavigate, useParams } from "react-router-dom";

import { Button } from "../../../components/ui/button";
import { Card, CardContent } from "../../../components/ui/card";
import { StatusBadge } from "../../../components/ui/status-badge";
import { automationApiService } from "../../../services/automations";
import type { AutomationResponse } from "../../../types/automation";
import { AutomationSideNav } from "./components/AutomationSideNav";

function toBadgeStatus(status: AutomationResponse["status"]) {
  return status === "active" ? "active" : "inactive";
}

export function AutomationDetailLayout() {
  const { automationId } = useParams<{ automationId: string }>();
  const navigate = useNavigate();
  const [automation, setAutomation] = useState<AutomationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadAutomation = useCallback(async () => {
    if (!automationId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await automationApiService.getAutomation(automationId);
      setAutomation(data);
    } catch (err) {
      console.error("Error loading automation:", err);
      setError("Failed to load automation. It may not exist or you don't have access.");
      setAutomation(null);
    } finally {
      setLoading(false);
    }
  }, [automationId]);

  useEffect(() => {
    void loadAutomation();
  }, [loadAutomation]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--gradient-start)] border-t-transparent" />
      </div>
    );
  }

  if (error || !automation) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => navigate("/dashboard/automations")}>
            <ChevronLeft className="h-5 w-5" />
          </Button>
          <h1 className="text-xl font-semibold text-[var(--text-primary)]">Automation Not Found</h1>
        </div>
        <Card>
          <CardContent className="p-12">
            <div className="text-center">
              <Workflow className="h-16 w-16 mx-auto text-[var(--text-muted)] mb-4" />
              <p className="text-[var(--text-muted)] mb-6">{error ?? "Failed to load automation."}</p>
              <Button onClick={() => navigate("/dashboard/automations")}>Back to Automations</Button>
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
            <Link to="/dashboard/automations">
              <ChevronLeft className="h-5 w-5" />
            </Link>
          </Button>
          <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-[var(--gradient-start)] to-[var(--gradient-mid)] flex items-center justify-center">
            <Workflow className="h-6 w-6 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-xl font-semibold text-[var(--text-primary)]">{automation.title}</h1>
              <StatusBadge status={toBadgeStatus(automation.status)} label={automation.status} />
            </div>
            <p className="text-sm text-[var(--text-muted)]">
              {automation.description || "Automation workflow"}
            </p>
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
        <AutomationSideNav />
        <div style={{ minWidth: 0 }}>
          <Outlet context={{ automation, reloadAutomation: loadAutomation }} />
        </div>
      </div>
    </div>
  );
}
