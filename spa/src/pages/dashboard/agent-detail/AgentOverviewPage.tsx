import { useEffect, useMemo, useState } from "react";
import type React from "react";
import { useNavigate } from "react-router-dom";
import {
  BookOpen,
  Check,
  CircleAlert,
  Copy,
  Key,
  Network,
  Pencil,
  Rocket,
  ShoppingBag,
  Wrench,
} from "lucide-react";

import { FieldGroup, Stack } from "../../../components/layout";
import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../../components/ui/card";
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
import { SchemaForm } from "../../../components/forms";
import { agentApiService, type Agent2AgentSharingResponse } from "../../../services/agents/AgentApiService";
import { agentMarketplaceApiService } from "../../../services/agentMarketplace";
import { knowledgeApiService } from "../../../services/knowledge";
import { skillApiService } from "../../../services/skills";
import type { FormSchema, FormValue } from "../../../types/form";
import type { KnowledgeBase } from "../../../types/knowledge";
import type { InstalledSkill } from "../../../types/skills";
import { useAgentDetailContext } from "./types";
import "./AgentOverviewPage.css";

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
  const [linkedKnowledgeBases, setLinkedKnowledgeBases] = useState<KnowledgeBase[]>([]);
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
        const [schema, skills, knowledgeBases] = await Promise.all([
          agentApiService.getUpdateSchema(agent.agent_id),
          skillApiService.listInstalledSkills(agent.agent_id),
          knowledgeApiService.listAgentKnowledgeBases(agent.agent_id),
        ]);
        if (!cancelled) {
          setUpdateSchema(schema);
          setInstalledSkills(skills);
          setLinkedKnowledgeBases(knowledgeBases);
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

  const enabledSkills = installedSkills.filter((skill) => skill.enabled);
  const registryUrl = deriveA2ARegistryUrl(a2aSharing);
  const hasActiveApiKey = Boolean(a2aSharing?.has_active_api_key);
  const isA2aEnabled = Boolean(a2aSharing?.enabled);
  const readinessItems = [
    {
      label: "Agent configured",
      complete: Boolean(currentAgent.agent_name && currentAgent.agent_persona),
      action: "Edit agent",
      onAction: () => setIsEditing(true),
    },
    {
      label: "API key ready",
      complete: hasActiveApiKey,
      action: "API keys",
      onAction: () => navigate(`/dashboard/agents/${agent.agent_id}/api-keys`),
    },
    {
      label: "A2A discovery enabled",
      complete: isA2aEnabled,
      action: "Enable",
      onAction: () => void handleToggleA2aSharing(true),
      disabled: updatingA2aSharing || loadingA2aSharing || !hasActiveApiKey,
    },
    {
      label: "Skills installed",
      complete: enabledSkills.length > 0,
      action: "Add skills",
      onAction: () => navigate(`/dashboard/agents/${agent.agent_id}/skills`),
    },
    {
      label: "Knowledge linked",
      complete: linkedKnowledgeBases.length > 0,
      action: "Link knowledge",
      onAction: () => navigate(`/dashboard/agents/${agent.agent_id}/knowledge-bases`),
    },
  ];

  return (
    <div className="agent-overview">
      <div className="agent-overview__toolbar">
        <div className="agent-overview__title-block">
          <p className="agent-overview__eyebrow">Agent Overview</p>
          <h2>{isEditing ? "Edit agent configuration" : currentAgent.agent_name}</h2>
          <p>{currentAgent.agent_description || "Review setup, sharing, and the next actions for this agent."}</p>
        </div>
        {!isEditing && (
          <div className="agent-overview__actions">
            <Button variant="outline" onClick={() => setPublishOpen(true)}>
              <ShoppingBag />
              Publish
            </Button>
            <Button onClick={() => setIsEditing(true)}>
              <Pencil />
              Edit
            </Button>
          </div>
        )}
      </div>

      {error && (
        <div className="agent-overview__error">
          {error}
        </div>
      )}

      {isEditing && updateSchema ? (
        <Card>
          <CardHeader>
            <CardTitle>Edit Agent</CardTitle>
            <CardDescription>Update the public name, description, model, and instructions for this agent.</CardDescription>
          </CardHeader>
          <CardContent>
            <SchemaForm
              schema={updateSchema}
              initialValues={initialValues}
              onSubmit={handleUpdate}
              onCancel={() => setIsEditing(false)}
              submitLabel="Save Changes"
              isLoading={isSubmitting}
            />
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="agent-overview__status-grid">
            <StatusCard
              icon={<Network />}
              label="A2A"
              value={isA2aEnabled ? "Enabled" : "Disabled"}
              tone={isA2aEnabled ? "good" : "muted"}
            />
            <StatusCard
              icon={<Key />}
              label="API key"
              value={hasActiveApiKey ? "Ready" : "Needed"}
              tone={hasActiveApiKey ? "good" : "warning"}
            />
            <StatusCard
              icon={<Wrench />}
              label="Skills"
              value={`${enabledSkills.length} active`}
              tone={enabledSkills.length ? "good" : "muted"}
            />
            <StatusCard
              icon={<BookOpen />}
              label="Knowledge"
              value={`${linkedKnowledgeBases.length} linked`}
              tone={linkedKnowledgeBases.length ? "good" : "muted"}
            />
          </div>

          <div className="agent-overview__grid">
            <div className="agent-overview__column">
              <Card className="agent-overview__panel agent-overview__readiness">
                <CardHeader>
                  <CardTitle>Readiness</CardTitle>
                  <CardDescription>Setup checks for a useful, shareable agent.</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="agent-overview__checklist">
                    {readinessItems.map((item) => (
                      <ReadinessItem key={item.label} {...item} />
                    ))}
                  </div>
                </CardContent>
              </Card>

              <Card className="agent-overview__panel agent-overview__a2a">
                <CardHeader>
                  <div className="agent-overview__panel-heading">
                    <div>
                      <CardTitle>Agent2Agent</CardTitle>
                      <CardDescription>Expose this agent through the custom registry and scoped Agent Card.</CardDescription>
                    </div>
                    <label className="agent-overview__toggle">
                      <Checkbox
                        checked={Boolean(a2aSharing?.enabled)}
                        disabled={loadingA2aSharing || updatingA2aSharing}
                        onChange={(event) => handleToggleA2aSharing(event.target.checked)}
                      />
                      Enabled
                    </label>
                  </div>
                </CardHeader>
                <CardContent>
                  {a2aError && (
                    <div className="agent-overview__error agent-overview__error--compact">
                      {a2aError}
                    </div>
                  )}

                  {a2aSharing && !a2aSharing.has_active_api_key && (
                    <div className="agent-overview__notice">
                      <div>
                        <Key />
                        <span>Create an active API key before enabling A2A discovery.</span>
                      </div>
                      <Button variant="outline" size="sm" onClick={() => navigate(`/dashboard/agents/${agent.agent_id}/api-keys`)}>
                        API Keys
                      </Button>
                    </div>
                  )}

                  {loadingA2aSharing ? (
                    <p className="agent-overview__muted">Loading Agent2Agent settings...</p>
                  ) : a2aSharing ? (
                    <div className="agent-overview__a2a-body">
                      {registryUrl && (
                        <CopyableA2AUrl
                          label="Registry URL"
                          value={registryUrl}
                          copied={copiedA2aUrl === "Registry URL"}
                          onCopy={handleCopyA2aUrl}
                        />
                      )}
                      <CopyableA2AUrl
                        label="Agent Card URL"
                        value={a2aSharing.agent_card_url}
                        copied={copiedA2aUrl === "Agent Card URL"}
                        onCopy={handleCopyA2aUrl}
                      />
                      <CopyableA2AUrl
                        label="Agent Service URL"
                        value={a2aSharing.service_url}
                        copied={copiedA2aUrl === "Agent Service URL"}
                        onCopy={handleCopyA2aUrl}
                      />

                      <div className="agent-overview__public-preview">
                        <span>Public discovery preview</span>
                        <strong>{currentAgent.agent_name}</strong>
                        <p>{currentAgent.agent_description || "InnomightLabs agent enabled for Agent2Agent communication."}</p>
                        <div>
                          <code>JSONRPC</code>
                          <code>chat</code>
                          <code>text/plain</code>
                        </div>
                      </div>
                    </div>
                  ) : null}
                </CardContent>
              </Card>

              <Card className="agent-overview__panel">
                <CardHeader>
                  <div className="agent-overview__panel-heading">
                    <div>
                      <CardTitle>Knowledge</CardTitle>
                      <CardDescription>Linked sources available for retrieval-augmented answers.</CardDescription>
                    </div>
                    <Button variant="outline" size="sm" onClick={() => navigate(`/dashboard/agents/${agent.agent_id}/knowledge-bases`)}>
                      Manage
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  {linkedKnowledgeBases.length ? (
                    <div className="agent-overview__list">
                      {linkedKnowledgeBases.slice(0, 4).map((kb) => (
                        <div key={kb.kb_id} className="agent-overview__list-item">
                          <BookOpen />
                          <div>
                            <strong>{kb.name}</strong>
                            <span>{kb.description || "Linked knowledge base"}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyPanel
                      icon={<BookOpen />}
                      title="No knowledge linked"
                      description="Attach knowledge bases so the agent can answer from your crawled content."
                      action="Link knowledge"
                      onAction={() => navigate(`/dashboard/agents/${agent.agent_id}/knowledge-bases`)}
                    />
                  )}
                </CardContent>
              </Card>
            </div>

            <div className="agent-overview__column">
              <Card className="agent-overview__panel agent-overview__details">
                <CardHeader>
                  <div className="agent-overview__panel-heading">
                    <div>
                      <CardTitle>Configuration</CardTitle>
                      <CardDescription>Core runtime settings and public description.</CardDescription>
                    </div>
                    <Button variant="outline" size="sm" onClick={() => setIsEditing(true)}>
                      <Pencil />
                      Edit
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="agent-overview__detail-grid">
                    <DetailItem label="Provider" value={currentAgent.agent_provider} />
                    <DetailItem label="Model" value={currentAgent.agent_model || "Default"} />
                    <DetailItem label="Architecture" value={currentAgent.agent_architecture} />
                    <DetailItem label="Created" value={formatDate(currentAgent.created_at)} />
                    <DetailItem label="Updated" value={currentAgent.updated_at ? formatDate(currentAgent.updated_at) : "Not updated"} />
                  </div>
                  <div className="agent-overview__description-block">
                    <span>Instructions Preview</span>
                    <p>{currentAgent.agent_persona}</p>
                  </div>
                </CardContent>
              </Card>

              <Card className="agent-overview__panel">
                <CardHeader>
                  <div className="agent-overview__panel-heading">
                    <div>
                      <CardTitle>Skills</CardTitle>
                      <CardDescription>Installed actions this agent can use during conversations.</CardDescription>
                    </div>
                    <Button variant="outline" size="sm" onClick={() => navigate(`/dashboard/agents/${agent.agent_id}/skills`)}>
                      Manage
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  {enabledSkills.length ? (
                    <div className="agent-overview__list">
                      {enabledSkills.slice(0, 4).map((skill) => (
                        <div key={skill.installed_skill_id} className="agent-overview__list-item">
                          <Wrench />
                          <div>
                            <strong>{skill.name}</strong>
                            <span>{skill.description}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyPanel
                      icon={<Wrench />}
                      title="No active skills"
                      description="Add skills to let this agent call tools, APIs, and platform workflows."
                      action="Add skills"
                      onAction={() => navigate(`/dashboard/agents/${agent.agent_id}/skills`)}
                    />
                  )}
                </CardContent>
              </Card>

              <Card className="agent-overview__panel agent-overview__marketplace">
                <CardHeader>
                  <div className="agent-overview__panel-heading">
                    <div>
                      <CardTitle>Marketplace</CardTitle>
                      <CardDescription>Publish a reusable template without copying private secrets.</CardDescription>
                    </div>
                    <Rocket className="agent-overview__panel-icon" />
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="agent-overview__muted">
                    Package this agent's public instructions and selected skill setup for other users to import.
                  </p>
                  <Button variant="outline" onClick={() => setPublishOpen(true)}>
                    <ShoppingBag />
                    Publish template
                  </Button>
                </CardContent>
              </Card>
            </div>
          </div>
        </>
      )}

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
    </div>
  );
}

interface CopyableA2AUrlProps {
  label: string;
  value: string;
  copied: boolean;
  onCopy: (label: string, value: string) => void;
}

interface StatusCardProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone: "good" | "warning" | "muted";
}

function StatusCard({ icon, label, value, tone }: StatusCardProps) {
  return (
    <Card className={`agent-overview__status-card agent-overview__status-card--${tone}`}>
      <div className="agent-overview__status-icon">{icon}</div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
    </Card>
  );
}

interface ReadinessItemProps {
  label: string;
  complete: boolean;
  action: string;
  onAction: () => void;
  disabled?: boolean;
}

function ReadinessItem({ label, complete, action, onAction, disabled }: ReadinessItemProps) {
  return (
    <div className="agent-overview__checklist-item">
      <div className={complete ? "agent-overview__check agent-overview__check--done" : "agent-overview__check"}>
        {complete ? <Check /> : <CircleAlert />}
      </div>
      <span>{label}</span>
      {complete ? (
        <small>Ready</small>
      ) : (
        <Button variant="ghost" size="sm" onClick={onAction} disabled={disabled}>
          {action}
        </Button>
      )}
    </div>
  );
}

function DetailItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="agent-overview__detail-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

interface EmptyPanelProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  action: string;
  onAction: () => void;
}

function EmptyPanel({ icon, title, description, action, onAction }: EmptyPanelProps) {
  return (
    <div className="agent-overview__empty">
      <div className="agent-overview__empty-icon">{icon}</div>
      <strong>{title}</strong>
      <p>{description}</p>
      <Button variant="outline" size="sm" onClick={onAction}>
        {action}
      </Button>
    </div>
  );
}

function CopyableA2AUrl({ label, value, copied, onCopy }: CopyableA2AUrlProps) {
  return (
    <div className="agent-overview__copy-row">
      <p>{label}</p>
      <div>
        <code>{value}</code>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => onCopy(label, value)}
          aria-label={`Copy ${label}`}
        >
          {copied ? <Check className="h-4 w-4 text-green-400" /> : <Copy className="h-4 w-4" />}
        </Button>
      </div>
    </div>
  );
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function deriveA2ARegistryUrl(sharing: Agent2AgentSharingResponse | null): string {
  const sourceUrl = sharing?.service_url || sharing?.agent_card_url;
  if (!sourceUrl) return "";
  try {
    const parsed = new URL(sourceUrl);
    return `${parsed.origin}/a2a/agents`;
  } catch {
    return "";
  }
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <FieldGroup>
      <Label>{label}</Label>
      {children}
    </FieldGroup>
  );
}
