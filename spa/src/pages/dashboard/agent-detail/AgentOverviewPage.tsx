import { useEffect, useMemo, useState } from "react";
import { Pencil } from "lucide-react";

import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { SchemaForm, SchemaView } from "../../../components/forms";
import { agentApiService } from "../../../services/agents/AgentApiService";
import type { FormSchema, FormValue } from "../../../types/form";
import { useAgentDetailContext } from "./types";

export function AgentOverviewPage() {
  const { agent } = useAgentDetailContext();
  const [currentAgent, setCurrentAgent] = useState(agent);
  const [isEditing, setIsEditing] = useState(false);
  const [updateSchema, setUpdateSchema] = useState<FormSchema | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setCurrentAgent(agent);
  }, [agent]);

  useEffect(() => {
    let cancelled = false;

    async function loadUpdateSchema() {
      try {
        const schema = await agentApiService.getUpdateSchema(agent.agent_id);
        if (!cancelled) {
          setUpdateSchema(schema);
        }
      } catch (err) {
        console.error("Error loading update schema:", err);
      }
    }

    loadUpdateSchema();

    return () => {
      cancelled = true;
    };
  }, [agent.agent_id]);

  const initialValues = useMemo(() => {
    const values: Record<string, string> = {};
    if (!updateSchema) return values;

    for (const field of updateSchema.form_inputs) {
      if (field.input_type === "password") {
        values[field.name] = "";
        continue;
      }
      const value = (currentAgent as unknown as Record<string, unknown>)[field.name];
      values[field.name] = value != null ? String(value) : "";
    }

    return values;
  }, [currentAgent, updateSchema]);

  const handleUpdate = async (data: Record<string, FormValue>) => {
    setIsSubmitting(true);
    setError(null);

    try {
      const payload: Record<string, string> = {};
      for (const [key, value] of Object.entries(data)) {
        if (typeof value === "string") {
          payload[key] = value;
        }
      }

      const updated = await agentApiService.updateAgent(agent.agent_id, payload);
      setCurrentAgent(updated);
      setIsEditing(false);
    } catch (err) {
      console.error("Error updating agent:", err);
      setError("Failed to update agent. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <CardTitle className="text-lg">{isEditing ? "Edit Agent" : "Agent Details"}</CardTitle>
          {!isEditing && (
            <Button variant="outline" onClick={() => setIsEditing(true)}>
              <Pencil className="h-4 w-4 mr-2" />
              Edit
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {error && (
          <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
            {error}
          </div>
        )}

        {isEditing && updateSchema ? (
          <SchemaForm
            schema={updateSchema}
            initialValues={initialValues}
            onSubmit={handleUpdate}
            onCancel={() => setIsEditing(false)}
            submitLabel="Save Changes"
            isLoading={isSubmitting}
          />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            <div>
              <p style={{ color: "var(--text-muted)", marginBottom: "0.5rem", display: "block", fontSize: "0.875rem" }}>
                Agent Name
              </p>
              <p style={{ color: "var(--text-primary)", fontSize: "1rem" }}>
                {currentAgent.agent_name}
              </p>
            </div>

            {updateSchema && (
              <SchemaView
                schema={updateSchema}
                data={currentAgent as unknown as Record<string, unknown>}
              />
            )}

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "1rem",
                paddingTop: "1.5rem",
                borderTop: "1px solid var(--border-subtle)",
              }}
            >
              <div>
                <p style={{ color: "var(--text-muted)", marginBottom: "0.5rem", display: "block", fontSize: "0.875rem" }}>
                  Created
                </p>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>
                  {new Date(currentAgent.created_at).toLocaleDateString()}
                </p>
              </div>
              {currentAgent.updated_at && (
                <div>
                  <p style={{ color: "var(--text-muted)", marginBottom: "0.5rem", display: "block", fontSize: "0.875rem" }}>
                    Last Updated
                  </p>
                  <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>
                    {new Date(currentAgent.updated_at).toLocaleDateString()}
                  </p>
                </div>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
