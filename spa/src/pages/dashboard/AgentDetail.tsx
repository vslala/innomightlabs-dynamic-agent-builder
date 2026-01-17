import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Bot, ChevronLeft, Pencil } from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Label } from "../../components/ui/label";
import { SchemaForm, SchemaView } from "../../components/forms";
import {
  agentApiService,
  type AgentResponse,
} from "../../services/agents/AgentApiService";
import type { FormSchema } from "../../types/form";

export function AgentDetail() {
  const { agentId } = useParams<{ agentId: string }>();
  const navigate = useNavigate();
  const [agent, setAgent] = useState<AgentResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Edit mode
  const [isEditing, setIsEditing] = useState(false);
  const [updateSchema, setUpdateSchema] = useState<FormSchema | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const loadAgent = async () => {
    if (!agentId) return;
    try {
      setError(null);
      const data = await agentApiService.getAgent(agentId);
      setAgent(data);
    } catch (err) {
      setError("Failed to load agent. It may not exist or you don't have access.");
      console.error("Error loading agent:", err);
    } finally {
      setLoading(false);
    }
  };

  const loadUpdateSchema = async () => {
    if (!agentId) return;
    try {
      const schema = await agentApiService.getUpdateSchema(agentId);
      setUpdateSchema(schema);
    } catch (err) {
      console.error("Error loading update schema:", err);
    }
  };

  useEffect(() => {
    loadAgent();
    loadUpdateSchema();
  }, [agentId]);

  const handleStartEdit = () => {
    setIsEditing(true);
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
  };

  const handleUpdate = async (data: Record<string, string>) => {
    if (!agentId) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const updated = await agentApiService.updateAgent(agentId, data);
      setAgent(updated);
      setIsEditing(false);
    } catch (err) {
      setError("Failed to update agent. Please try again.");
      console.error("Error updating agent:", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--gradient-start)] border-t-transparent" />
      </div>
    );
  }

  if (error && !agent) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate("/dashboard/agents")}
          >
            <ChevronLeft className="h-5 w-5" />
          </Button>
          <h1 className="text-xl font-semibold text-[var(--text-primary)]">
            Agent Not Found
          </h1>
        </div>
        <Card>
          <CardContent className="p-12">
            <div className="text-center">
              <Bot className="h-16 w-16 mx-auto text-[var(--text-muted)] mb-4" />
              <p className="text-[var(--text-muted)] mb-6">{error}</p>
              <Button onClick={() => navigate("/dashboard/agents")}>
                Back to Agents
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!agent) return null;

  // Dynamically build initial values from schema fields and agent data
  const initialValues: Record<string, string> = {};
  if (updateSchema) {
    for (const field of updateSchema.form_inputs) {
      // Get value from agent data, or empty string for password fields
      const fieldName = field.name;
      if (field.input_type === "password") {
        // Password fields are not returned by backend, leave empty
        initialValues[fieldName] = "";
      } else {
        // Dynamically get the value from agent object
        const value = (agent as unknown as Record<string, unknown>)[fieldName];
        initialValues[fieldName] = value != null ? String(value) : "";
      }
    }
  }

  return (
    <div style={{ maxWidth: "42rem", display: "flex", flexDirection: "column", gap: "2rem" }}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate("/dashboard/agents")}
          >
            <ChevronLeft className="h-5 w-5" />
          </Button>
          <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-[var(--gradient-start)] to-[var(--gradient-mid)] flex items-center justify-center">
            <Bot className="h-6 w-6 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-[var(--text-primary)]">
              {agent.agent_name}
            </h1>
            <p className="text-sm text-[var(--text-muted)]">
              {agent.agent_provider}
            </p>
          </div>
        </div>
        {!isEditing && (
          <Button variant="outline" onClick={handleStartEdit}>
            <Pencil className="h-4 w-4 mr-2" />
            Edit
          </Button>
        )}
      </div>

      {/* Agent Info / Edit Form */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">
            {isEditing ? "Edit Agent" : "Agent Details"}
          </CardTitle>
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
              onCancel={handleCancelEdit}
              submitLabel="Save Changes"
              isLoading={isSubmitting}
            />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
              {/* Agent name is always shown (not in update schema) */}
              <div>
                <Label style={{ color: "var(--text-muted)", marginBottom: "0.5rem", display: "block" }}>
                  Agent Name
                </Label>
                <p style={{ color: "var(--text-primary)", fontSize: "1rem" }}>
                  {agent.agent_name}
                </p>
              </div>

              {/* Dynamically render fields from schema */}
              {updateSchema && (
                <SchemaView
                  schema={updateSchema}
                  data={agent as unknown as Record<string, unknown>}
                />
              )}

              {/* Timestamps are metadata, always shown */}
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
                  <Label style={{ color: "var(--text-muted)", marginBottom: "0.5rem", display: "block" }}>
                    Created
                  </Label>
                  <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>
                    {new Date(agent.created_at).toLocaleDateString()}
                  </p>
                </div>
                {agent.updated_at && (
                  <div>
                    <Label style={{ color: "var(--text-muted)", marginBottom: "0.5rem", display: "block" }}>
                      Last Updated
                    </Label>
                    <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>
                      {new Date(agent.updated_at).toLocaleDateString()}
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
