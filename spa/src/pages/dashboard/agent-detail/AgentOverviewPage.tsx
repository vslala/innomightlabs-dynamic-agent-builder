import { useEffect, useMemo, useState } from "react";
import type React from "react";
import { useNavigate } from "react-router-dom";
import { Pencil, ShoppingBag } from "lucide-react";

import { FieldGroup, Stack } from "../../../components/layout";
import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Checkbox,
  Input,
  Label,
  Textarea,
} from "../../../components/ui";
import { SchemaForm, SchemaView } from "../../../components/forms";
import { agentApiService } from "../../../services/agents/AgentApiService";
import { agentMarketplaceApiService } from "../../../services/agentMarketplace";
import { skillApiService } from "../../../services/skills";
import type { FormSchema, FormValue } from "../../../types/form";
import type { InstalledSkill } from "../../../types/skills";
import { useAgentDetailContext } from "./types";

export function AgentOverviewPage() {
  const { agent } = useAgentDetailContext();
  const navigate = useNavigate();
  const [currentAgent, setCurrentAgent] = useState(agent);
  const [isEditing, setIsEditing] = useState(false);
  const [updateSchema, setUpdateSchema] = useState<FormSchema | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [publishOpen, setPublishOpen] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [installedSkills, setInstalledSkills] = useState<InstalledSkill[]>([]);
  const [publishForm, setPublishForm] = useState({
    title: agent.agent_name,
    short_description: agent.agent_description || "",
    full_description: agent.agent_description || agent.agent_persona,
    tags: "",
    included_skill_ids: [] as string[],
  });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setCurrentAgent(agent);
  }, [agent]);

  useEffect(() => {
    let cancelled = false;

    async function loadPageData() {
      try {
        const [schema, skills] = await Promise.all([
          agentApiService.getUpdateSchema(agent.agent_id),
          skillApiService.listInstalledSkills(agent.agent_id),
        ]);
        if (!cancelled) {
          setUpdateSchema(schema);
          setInstalledSkills(skills);
          setPublishForm((current) => ({
            ...current,
            included_skill_ids: skills.map((skill) => skill.installed_skill_id),
          }));
        }
      } catch (err) {
        console.error("Error loading agent overview data:", err);
      }
    }

    loadPageData();

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

  const handlePublish = async () => {
    setPublishing(true);
    setError(null);
    try {
      const published = await agentMarketplaceApiService.publishAgent({
        agent_id: currentAgent.agent_id,
        title: publishForm.title,
        short_description: publishForm.short_description,
        full_description: publishForm.full_description,
        tags: publishForm.tags.split(",").map((tag) => tag.trim()).filter(Boolean),
        included_skill_ids: publishForm.included_skill_ids,
        status: "published",
      });
      navigate(`/dashboard/agents/marketplace/${published.template_id}`);
    } catch (err) {
      console.error("Error publishing agent:", err);
      setError("Failed to publish agent. Please check the required fields and try again.");
    } finally {
      setPublishing(false);
    }
  };

  const togglePublishSkill = (installedSkillId: string) => {
    setPublishForm((current) => {
      const included = new Set(current.included_skill_ids);
      if (included.has(installedSkillId)) {
        included.delete(installedSkillId);
      } else {
        included.add(installedSkillId);
      }
      return { ...current, included_skill_ids: Array.from(included) };
    });
  };

  return (
    <Card>
      <CardHeader>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <CardTitle className="text-lg">{isEditing ? "Edit Agent" : "Agent Details"}</CardTitle>
          {!isEditing && (
            <div className="flex gap-3">
              <Button variant="outline" onClick={() => setPublishOpen(true)}>
                <ShoppingBag className="h-4 w-4" />
                Publish
              </Button>
              <Button variant="outline" onClick={() => setIsEditing(true)}>
                <Pencil className="h-4 w-4" />
                Edit
              </Button>
            </div>
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

      <Dialog open={publishOpen} onOpenChange={setPublishOpen}>
        <DialogContent className="max-h-[88vh] max-w-2xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Publish to Marketplace</DialogTitle>
            <DialogDescription>
              Share a reusable agent template. Skill secrets and OAuth credentials are never published.
            </DialogDescription>
          </DialogHeader>

          <DialogBody>
            <Field label="Title">
              <Input
                value={publishForm.title}
                onChange={(event) => setPublishForm((current) => ({ ...current, title: event.target.value }))}
              />
            </Field>
            <Field label="Short description">
              <Input
                value={publishForm.short_description}
                onChange={(event) => setPublishForm((current) => ({ ...current, short_description: event.target.value }))}
              />
            </Field>
            <Field label="Full description">
              <Textarea
                value={publishForm.full_description}
                onChange={(event) => setPublishForm((current) => ({ ...current, full_description: event.target.value }))}
              />
            </Field>
            <Field label="Tags">
              <Input
                value={publishForm.tags}
                placeholder="league-of-legends, coaching, productivity"
                onChange={(event) => setPublishForm((current) => ({ ...current, tags: event.target.value }))}
              />
            </Field>

            <FieldGroup>
              <Label>Included skills</Label>
              {installedSkills.length === 0 ? (
                <p className="text-sm text-[var(--text-muted)]">This agent has no installed skills.</p>
              ) : (
                <Stack gap="sm">
                  {installedSkills.map((skill) => (
                    <label
                      key={skill.installed_skill_id}
                      className="flex cursor-pointer items-start rounded-lg border border-[var(--border-default)] bg-[var(--surface-control)]"
                      style={{ gap: "var(--space-3)", padding: "var(--space-4)" }}
                    >
                      <Checkbox
                        checked={publishForm.included_skill_ids.includes(skill.installed_skill_id)}
                        onChange={() => togglePublishSkill(skill.installed_skill_id)}
                        className="mt-1 shrink-0"
                      />
                      <span className="min-w-0">
                        <span className="block text-sm font-medium text-[var(--text-primary)]">{skill.name}</span>
                        <span className="block text-xs leading-5 text-[var(--text-muted)]">{skill.description}</span>
                      </span>
                    </label>
                  ))}
                </Stack>
              )}
            </FieldGroup>
          </DialogBody>

          <DialogFooter>
            <Button variant="outline" onClick={() => setPublishOpen(false)} disabled={publishing}>
              Cancel
            </Button>
            <Button
              onClick={handlePublish}
              disabled={publishing || !publishForm.title.trim() || !publishForm.short_description.trim() || !publishForm.full_description.trim()}
            >
              {publishing ? "Publishing..." : "Publish"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <FieldGroup>
      <Label>{label}</Label>
      {children}
    </FieldGroup>
  );
}
