/**
 * Keeps links to the old triggers, runs, and analytics routes working.
 *
 * Those surfaces are now panels inside the workspace, so the route redirects to
 * the workspace with the matching panel state, preserving any `run` id.
 */

import { Navigate, useParams, useSearchParams } from "react-router-dom";

export function WorkspaceRedirect({
  panel,
  step,
}: {
  panel?: "runs" | "analytics";
  step?: "trigger";
}) {
  const { automationId } = useParams<{ automationId: string }>();
  const [params] = useSearchParams();

  const next = new URLSearchParams();
  if (panel) next.set("panel", panel);
  const runId = params.get("run");
  if (runId) next.set("run", runId);
  // The trigger card is keyed by the start node id, which only the workspace
  // knows, so ask it to expand the trigger instead of naming a step.
  if (step === "trigger") next.set("focus", "trigger");

  const query = next.toString();
  return (
    <Navigate to={`/dashboard/automations/${automationId}${query ? `?${query}` : ""}`} replace />
  );
}
