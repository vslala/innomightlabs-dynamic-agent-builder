/**
 * Publishing the agent as a marketplace template: title, descriptions, tags and which skills to include.
 * Skill secrets and OAuth credentials are never part of a template (the API strips them).
 */

import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { FieldGroup, Stack } from "../../../../components/layout";
import {
  Button,
  Checkbox,
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  Textarea,
} from "../../../../components/ui";
import type { AgentResponse } from "../../../../services/agents/AgentApiService";
import { agentMarketplaceApiService } from "../../../../services/agentMarketplace";
import type { InstalledSkill } from "../../../../types/skills";

export function PublishDialog({
  agent,
  skills,
  open,
  onOpenChange,
}: {
  agent: AgentResponse;
  skills: InstalledSkill[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[88vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Publish to Marketplace</DialogTitle>
          <DialogDescription>
            Share a reusable agent template. Skill secrets and OAuth credentials are never published.
          </DialogDescription>
        </DialogHeader>
        {/* Mounted only while open, so each opening starts from the agent as it is now */}
        {open && <PublishForm agent={agent} skills={skills} onCancel={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  );
}

function PublishForm({ agent, skills, onCancel }: { agent: AgentResponse; skills: InstalledSkill[]; onCancel: () => void }) {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    title: agent.agent_name,
    short_description: agent.agent_description || "",
    full_description: agent.agent_description || agent.agent_persona,
    tags: "",
    included_skill_ids: skills.map((skill) => skill.installed_skill_id),
  });
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (patch: Partial<typeof form>) => setForm((current) => ({ ...current, ...patch }));
  const complete = Boolean(form.title.trim() && form.short_description.trim() && form.full_description.trim());

  const toggleSkill = (installedSkillId: string) => {
    const included = new Set(form.included_skill_ids);
    if (included.has(installedSkillId)) included.delete(installedSkillId);
    else included.add(installedSkillId);
    set({ included_skill_ids: [...included] });
  };

  const publish = async () => {
    setPublishing(true);
    setError(null);
    try {
      const published = await agentMarketplaceApiService.publishAgent({
        agent_id: agent.agent_id,
        title: form.title,
        short_description: form.short_description,
        full_description: form.full_description,
        tags: form.tags.split(",").map((tag) => tag.trim()).filter(Boolean),
        included_skill_ids: form.included_skill_ids,
        status: "published",
      });
      navigate(`/dashboard/agents/marketplace/${published.template_id}`);
    } catch (err) {
      console.error("Error publishing agent:", err);
      setError("Failed to publish agent. Please check the required fields and try again.");
      setPublishing(false);
    }
  };

  return (
    <>
      <DialogBody>
        {error ? (
          <p className="agent-overview-error" role="alert">
            {error}
          </p>
        ) : null}
        <Field label="Title">
          <Input value={form.title} onChange={(event) => set({ title: event.target.value })} />
        </Field>
        <Field label="Short description">
          <Input value={form.short_description} onChange={(event) => set({ short_description: event.target.value })} />
        </Field>
        <Field label="Full description">
          <Textarea value={form.full_description} onChange={(event) => set({ full_description: event.target.value })} />
        </Field>
        <Field label="Tags">
          <Input
            value={form.tags}
            placeholder="league-of-legends, coaching, productivity"
            onChange={(event) => set({ tags: event.target.value })}
          />
        </Field>
        <FieldGroup>
          <Label>Included skills</Label>
          {skills.length === 0 ? (
            <p className="agent-overview-muted">This agent has no installed skills.</p>
          ) : (
            <Stack gap="sm">
              {skills.map((skill) => (
                <label key={skill.installed_skill_id} className="agent-overview-skill-choice">
                  <Checkbox
                    checked={form.included_skill_ids.includes(skill.installed_skill_id)}
                    onChange={() => toggleSkill(skill.installed_skill_id)}
                  />
                  <span>
                    <strong>{skill.name}</strong>
                    <small>{skill.description}</small>
                  </span>
                </label>
              ))}
            </Stack>
          )}
        </FieldGroup>
      </DialogBody>
      <DialogFooter>
        <Button variant="outline" onClick={onCancel} disabled={publishing}>
          Cancel
        </Button>
        <Button onClick={() => void publish()} disabled={publishing || !complete}>
          {publishing ? "Publishing..." : "Publish"}
        </Button>
      </DialogFooter>
    </>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <FieldGroup>
      <Label>{label}</Label>
      {children}
    </FieldGroup>
  );
}
