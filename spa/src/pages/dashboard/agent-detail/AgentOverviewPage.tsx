/**
 * An agent's overview: what it is for, what's left to set up, its instructions, everything it can use, and how
 * it is shared. Phone first; from a wide container the setup, sharing and details cards form a side column.
 *
 * The cards live in `overview/`. This page owns only the edit mode and where each setup action leads.
 */

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Pencil } from "lucide-react";

import { SchemaForm } from "../../../components/forms";
import { Button } from "../../../components/ui";
import { agentApiService, type AgentResponse } from "../../../services/agents/AgentApiService";
import type { FormSchema, FormValue } from "../../../types/form";
import { CapabilitiesCard } from "./overview/CapabilitiesCard";
import { DetailsCard } from "./overview/DetailsCard";
import { InstructionsCard } from "./overview/InstructionsCard";
import { OverviewCard } from "./overview/OverviewCard";
import { PublishDialog } from "./overview/PublishDialog";
import { SetupCard } from "./overview/SetupCard";
import { setupChecks, type SetupAction } from "./overview/setupChecks";
import { ShareCard } from "./overview/ShareCard";
import { useOverviewData, type Loaded } from "./overview/useOverviewData";
import { useAgentDetailContext } from "./types";
import "./AgentOverviewPage.css";

export function AgentOverviewPage() {
  const { agent, onAgentUpdated } = useAgentDetailContext();
  const navigate = useNavigate();
  const data = useOverviewData(agent.agent_id);
  const [editing, setEditing] = useState(false);
  const [publishOpen, setPublishOpen] = useState(false);
  const agentPath = `/dashboard/agents/${agent.agent_id}`;

  const skills = data.skills.state === "ready" ? data.skills.value : [];
  const sharing = data.a2a.sharing.state === "ready" ? data.a2a.sharing.value : null;
  const checks = setupChecks({
    configured: Boolean(agent.agent_name && agent.agent_persona),
    hasActiveApiKey: Boolean(sharing?.has_active_api_key),
    a2aEnabled: Boolean(sharing?.enabled),
    activeSkills: skills.filter((skill) => skill.enabled).length,
    linkedKnowledgeBases: data.knowledgeBases.state === "ready" ? data.knowledgeBases.value.length : 0,
  });
  const setupComplete = checks.every((check) => check.done);

  const runSetupAction = (action: SetupAction) => {
    if (action === "edit") setEditing(true);
    else if (action === "enable-a2a") void data.a2a.setEnabled(true);
    else navigate(`${agentPath}/${action}`);
  };

  if (editing) {
    return (
      <div className="agent-overview-host">
        <EditAgent
          agent={agent}
          schema={data.updateSchema}
          onSaved={(updated) => {
            onAgentUpdated(updated);
            setEditing(false);
          }}
          onCancel={() => setEditing(false)}
        />
      </div>
    );
  }

  const setup = <SetupCard checks={checks} busy={data.a2a.updating} onAction={runSetupAction} />;

  return (
    <div className="agent-overview-host">
      <div className="agent-overview">
        <section className="agent-overview-intro" aria-label="About this agent">
          <p>{agent.agent_description || "No description yet. Add one so people know what this agent is for."}</p>
          <Button onClick={() => setEditing(true)}>
            <Pencil />
            Edit
          </Button>
        </section>

        <div className="agent-overview__main">
          {!setupComplete && setup}
          <InstructionsCard
            instructions={agent.agent_persona}
            onSave={async (instructions) => {
              onAgentUpdated(await agentApiService.updateAgent(agent.agent_id, { agent_persona: instructions }));
            }}
          />
          <CapabilitiesCard
            agentPath={agentPath}
            skills={data.skills}
            knowledgeBases={data.knowledgeBases}
            mcpConnections={data.mcpConnections}
            memoryBlocks={data.memoryBlocks}
          />
        </div>

        <div className="agent-overview__side">
          {setupComplete && setup}
          <ShareCard agent={agent} a2a={data.a2a} apiKeysPath={`${agentPath}/api-keys`} onPublish={() => setPublishOpen(true)} />
          <DetailsCard agent={agent} />
        </div>
      </div>

      <PublishDialog agent={agent} skills={skills} open={publishOpen} onOpenChange={setPublishOpen} />
    </div>
  );
}

function EditAgent({
  agent,
  schema,
  onSaved,
  onCancel,
}: {
  agent: AgentResponse;
  schema: Loaded<FormSchema>;
  onSaved: (agent: AgentResponse) => void;
  onCancel: () => void;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const initialValues = useMemo(() => {
    const values: Record<string, string> = {};
    const fields = schema.state === "ready" ? schema.value.form_inputs : [];
    for (const field of fields) {
      // Secrets are write-only: an empty field leaves the stored one alone
      const value = field.input_type === "password" ? null : (agent as unknown as Record<string, unknown>)[field.name];
      values[field.name] = value != null ? String(value) : "";
    }
    return values;
  }, [agent, schema]);

  const save = async (values: Record<string, FormValue>) => {
    setSaving(true);
    setError(null);
    try {
      const payload = Object.fromEntries(
        Object.entries(values).filter((entry): entry is [string, string] => typeof entry[1] === "string")
      );
      onSaved(await agentApiService.updateAgent(agent.agent_id, payload));
    } catch (err) {
      console.error("Error updating agent:", err);
      setError("Failed to update agent. Please try again.");
      setSaving(false);
    }
  };

  return (
    <OverviewCard id="agent-edit" title="Edit agent">
      <p className="agent-overview-muted">Update the public name, description, model, and instructions for this agent.</p>
      {error ? (
        <p className="agent-overview-error" role="alert">
          {error}
        </p>
      ) : null}
      {schema.state === "ready" ? (
        <SchemaForm
          schema={schema.value}
          initialValues={initialValues}
          onSubmit={save}
          onCancel={onCancel}
          submitLabel="Save Changes"
          isLoading={saving}
        />
      ) : schema.state === "failed" ? (
        <p className="agent-overview-error" role="alert">
          Couldn't load the edit form. Reload the page to try again.
        </p>
      ) : (
        <p className="agent-overview-muted">Loading the form…</p>
      )}
    </OverviewCard>
  );
}
