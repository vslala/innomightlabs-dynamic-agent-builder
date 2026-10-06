/**
 * The dashboard route for one automation: the workspace backed by the API.
 *
 * Panel state lives in the query string (`?step=`, `?panel=`, `?run=`) so
 * everything stays deep-linkable.
 */

import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { automationApiService } from "../../../services/automations";
import { AutomationWorkspace, type WorkspaceOperations } from "./AutomationWorkspace";
import { apiChainGateway } from "./components/chainGateway";
import { useAutomationDraft } from "./hooks/useAutomationDraft";
import { useAutomationRuns } from "./hooks/useAutomationRuns";
import { useWorkspaceParams } from "./hooks/useWorkspaceParams";
import { useAutomationDetailContext } from "./types";

export function AutomationWorkspacePage() {
  const { automationId = "" } = useParams<{ automationId: string }>();
  const navigate = useNavigate();
  const { automation, reloadAutomation, openPublishDialog } = useAutomationDetailContext();
  const params = useWorkspaceParams();
  const draft = useAutomationDraft(automationId);
  const runs = useAutomationRuns(automationId);
  const gateway = useMemo(() => apiChainGateway(automationId), [automationId]);

  const operations = useMemo<WorkspaceOperations>(
    () => ({
      changeStatus: async (status) => {
        await automationApiService.updateAutomation(automationId, { status });
        await reloadAutomation();
      },
      rename: async (title) => {
        await automationApiService.updateAutomation(automationId, { title });
        await reloadAutomation();
      },
      deleteAutomation: async () => {
        await automationApiService.deleteAutomation(automationId);
        navigate("/dashboard/automations");
      },
      publish: openPublishDialog,
      enableSkill: (skillId, config) => automationApiService.enableSkill(automationId, skillId, { config }),
    }),
    [automationId, navigate, openPublishDialog, reloadAutomation]
  );

  return (
    <AutomationWorkspace
      automation={automation}
      draft={draft}
      runs={runs}
      params={params}
      gateway={gateway}
      operations={operations}
    />
  );
}
