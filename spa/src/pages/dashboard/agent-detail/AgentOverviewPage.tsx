import { useEffect, useMemo, useState } from "react";
import type React from "react";
import { useNavigate } from "react-router-dom";
import { Check, Copy, Key, Network, Pencil, ShoppingBag } from "lucide-react";

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
import { agentApiService, type Agent2AgentSharingResponse } from "../../../services/agents/AgentApiService";
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
  const [a2aSharing, setA2aSharing] = useState<Agent2AgentSharingResponse | null>(null);
  const [loadingA2aSharing, setLoadingA2aSharing] = useState(false);
  const [updatingA2aSharing, setUpdatingA2aSharing] = useState(false);
  const [a2aError, setA2aError] = useState<string | null>(null);
  const [copiedA2aUrl, setCopiedA2aUrl] = useState<string | null>(null);
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

  useEffect(() => {
    let cancelled = false;

    async function loadA2aSharing() {
      setLoadingA2aSharing(true);
      setA2aError(null);
      try {
        const sharing = await agentApiService.getAgent2AgentSharing(agent.agent_id);
        if (!cancelled) {
          setA2aSharing(sharing);
        }
      } catch (err) {
        console.error("Error loading Agent2Agent sharing settings:", err);
        if (!cancelled) {
          setA2aError("Failed to load Agent2Agent settings.");
        }
      } finally {
        if (!cancelled) {
          setLoadingA2aSharing(false);
        }
      }
    }

    loadA2aSharing();

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

  const handleToggleA2aSharing = async (enabled: boolean) => {
    setUpdatingA2aSharing(true);
    setA2aError(null);
    try {
      const sharing = await agentApiService.updateAgent2AgentSharing(agent.agent_id, enabled);
      setA2aSharing(sharing);
      setCurrentAgent((current) => ({
        ...current,
        is_agent2agent_enabled: sharing.enabled,
      }));
    } catch (err) {
      console.error("Error updating Agent2Agent sharing settings:", err);
      setA2aError(err instanceof Error ? err.message : "Failed to update Agent2Agent settings.");
    } finally {
      setUpdatingA2aSharing(false);
    }
  };

  const handleCopyA2aUrl = async (label: string, value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopiedA2aUrl(label);
      setTimeout(() => setCopiedA2aUrl(null), 2000);
    } catch (err) {
      console.error("Failed to copy Agent2Agent URL:", err);
    }
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

            <div
              style={{
                borderTop: "1px solid var(--border-subtle)",
                paddingTop: "1.5rem",
              }}
            >
              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "1rem", marginBottom: "1rem" }}>
                <div style={{ display: "flex", alignItems: "flex-start", gap: "0.75rem" }}>
                  <div
                    style={{
                      height: "2.25rem",
                      width: "2.25rem",
                      borderRadius: "0.5rem",
                      backgroundColor: "var(--bg-tertiary)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0,
                    }}
                  >
                    <Network className="h-4 w-4 text-[var(--gradient-start)]" />
                  </div>
                  <div>
                    <p style={{ color: "var(--text-primary)", fontWeight: 600, marginBottom: "0.25rem" }}>
                      Agent2Agent Discovery
                    </p>
                    <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", lineHeight: 1.5 }}>
                      Share this agent through the public A2A facilitator card. Calls still require an active API key for this agent.
                    </p>
                  </div>
                </div>
                <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: "var(--text-secondary)", fontSize: "0.875rem", whiteSpace: "nowrap" }}>
                  <Checkbox
                    checked={Boolean(a2aSharing?.enabled)}
                    disabled={loadingA2aSharing || updatingA2aSharing}
                    onChange={(event) => handleToggleA2aSharing(event.target.checked)}
                  />
                  Enabled
                </label>
              </div>

              {a2aError && (
                <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                  {a2aError}
                </div>
              )}

              {a2aSharing && !a2aSharing.has_active_api_key && (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: "1rem",
                    marginBottom: "1rem",
                    padding: "0.875rem",
                    border: "1px solid rgba(234, 179, 8, 0.25)",
                    borderRadius: "0.5rem",
                    backgroundColor: "rgba(234, 179, 8, 0.08)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: "var(--text-secondary)", fontSize: "0.875rem" }}>
                    <Key className="h-4 w-4 text-yellow-400" />
                    <span>Create an active API key before enabling A2A discovery.</span>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => navigate(`/dashboard/agents/${agent.agent_id}/api-keys`)}>
                    API Keys
                  </Button>
                </div>
              )}

              {loadingA2aSharing ? (
                <div style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
                  Loading Agent2Agent settings...
                </div>
              ) : a2aSharing ? (
                <div style={{ display: "grid", gap: "0.75rem" }}>
                  <CopyableA2AUrl
                    label="Facilitator card"
                    value={a2aSharing.agent_card_url}
                    copied={copiedA2aUrl === "Facilitator card"}
                    onCopy={handleCopyA2aUrl}
                  />
                  <CopyableA2AUrl
                    label="Agent service"
                    value={a2aSharing.service_url}
                    copied={copiedA2aUrl === "Agent service"}
                    onCopy={handleCopyA2aUrl}
                  />
                  <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", lineHeight: 1.5 }}>
                    The public card uses this agent's name and description. Use Edit above to change what other A2A clients discover.
                  </p>
                </div>
              ) : null}
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

interface CopyableA2AUrlProps {
  label: string;
  value: string;
  copied: boolean;
  onCopy: (label: string, value: string) => void;
}

function CopyableA2AUrl({ label, value, copied, onCopy }: CopyableA2AUrlProps) {
  return (
    <div>
      <p style={{ color: "var(--text-muted)", marginBottom: "0.375rem", fontSize: "0.75rem" }}>
        {label}
      </p>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.5rem",
          minWidth: 0,
          fontFamily: "monospace",
          fontSize: "0.8125rem",
          backgroundColor: "var(--bg-tertiary)",
          border: "1px solid var(--border-subtle)",
          padding: "0.5rem 0.75rem",
          borderRadius: "0.375rem",
        }}
      >
        <code style={{ color: "var(--text-secondary)", flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {value}
        </code>
        <Button
          variant="ghost"
          size="icon"
          style={{ height: "1.5rem", width: "1.5rem" }}
          onClick={() => onCopy(label, value)}
          aria-label={`Copy ${label}`}
        >
          {copied ? <Check className="h-4 w-4 text-green-400" /> : <Copy className="h-4 w-4" />}
        </Button>
      </div>
    </div>
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
