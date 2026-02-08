import { useEffect, useState } from "react";
import { ToggleLeft, ToggleRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { SchemaForm } from "../../components/forms";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../../components/ui/dialog";
import { skillsApiService, type SkillDefinitionResponse } from "../../services/skills";
import type { FormSchema, FormValue } from "../../types/form";

export function Skills() {
  const [skills, setSkills] = useState<SkillDefinitionResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadSchema, setUploadSchema] = useState<FormSchema | null>(null);
  const [manifestSchema, setManifestSchema] = useState<FormSchema | null>(null);
  const [creatingFromManifest, setCreatingFromManifest] = useState(false);

  const [editing, setEditing] = useState<SkillDefinitionResponse | null>(null);
  const [editSchema, setEditSchema] = useState<FormSchema | null>(null);
  const [editInitialValues, setEditInitialValues] = useState<Record<string, any> | null>(null);
  const [savingEdit, setSavingEdit] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const items = await skillsApiService.listSkills();
      // sort: active first, then by name
      items.sort((a, b) => {
        if (a.status !== b.status) return a.status === "active" ? -1 : 1;
        return a.name.localeCompare(b.name);
      });
      setSkills(items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load skills");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const loadSchema = async () => {
      try {
        const schema = await skillsApiService.getUploadSchema();
        setUploadSchema(schema);
        const m = await skillsApiService.getManifestSchema();
        setManifestSchema(m);
      } catch (e) {
        console.error("Failed to load skills schemas", e);
      }
    };
    void loadSchema();
  }, []);

  const handleUpload = async (file: File) => {
    setUploading(true);
    setError(null);
    try {
      await skillsApiService.uploadSkillZip(file);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const openEdit = async (skill: SkillDefinitionResponse) => {
    setEditing(skill);
    setEditSchema(null);
    setEditInitialValues(null);
    setError(null);
    try {
      const resp = await skillsApiService.getEditForm(skill.skill_id, skill.version);
      setEditSchema(resp.form_schema);
      setEditInitialValues(resp.initial_values || {});
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load edit form");
    }
  };

  const toggle = async (skill: SkillDefinitionResponse) => {
    try {
      const updated =
        skill.status === "active"
          ? await skillsApiService.deactivateSkill(skill.skill_id, skill.version)
          : await skillsApiService.activateSkill(skill.skill_id, skill.version);

      setSkills((prev) => prev.map((s) => (s.skill_id === updated.skill_id && s.version === updated.version ? updated : s)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update status");
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)" }}>Skills</h1>
          <p style={{ color: "var(--text-muted)", marginTop: "0.25rem" }}>
            Upload skill zips and activate/deactivate which skills are visible to the LLM.
          </p>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
        <Card>
          <CardHeader>
            <CardTitle>Upload Skill (.zip)</CardTitle>
          </CardHeader>
          <CardContent>
            {uploadSchema ? (
              <SchemaForm
                schema={uploadSchema}
                submitLabel={uploading ? "Uploading..." : "Upload"}
                isLoading={uploading}
                onSubmit={async (data: Record<string, FormValue>) => {
                  const fileValue = data.file;
                  const file = Array.isArray(fileValue)
                    ? fileValue.find((v): v is File => v instanceof File) || null
                    : fileValue instanceof FileList
                      ? fileValue.item(0)
                      : null;

                  if (!file) {
                    setError("Please select a .zip file");
                    return;
                  }

                  await handleUpload(file);
                }}
              />
            ) : (
              <p style={{ color: "var(--text-muted)" }}>Loading upload form…</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Create Skill (Manifest JSON)</CardTitle>
          </CardHeader>
          <CardContent>
            {manifestSchema ? (
              <SchemaForm
                schema={manifestSchema}
                submitLabel={creatingFromManifest ? "Creating..." : "Create"}
                isLoading={creatingFromManifest}
                onSubmit={async (data: Record<string, FormValue>) => {
                  const manifest_json = String(data.manifest_json || "");
                  const skill_md = String(data.skill_md || "");
                  const secrets = Array.isArray(data.secrets) ? data.secrets : [];

                  setCreatingFromManifest(true);
                  setError(null);
                  try {
                    await skillsApiService.createFromManifest({ manifest_json, skill_md, secrets: secrets as any });
                    await load();
                  } catch (e) {
                    setError(e instanceof Error ? e.message : "Failed to create skill");
                  } finally {
                    setCreatingFromManifest(false);
                  }
                }}
              />
            ) : (
              <p style={{ color: "var(--text-muted)" }}>Loading manifest form…</p>
            )}
          </CardContent>
        </Card>
      </div>

      {error && (
        <div style={{
          padding: "0.75rem",
          borderRadius: "0.5rem",
          backgroundColor: "rgba(239, 68, 68, 0.1)",
          border: "1px solid rgba(239, 68, 68, 0.2)",
          color: "#f87171",
          fontSize: "0.875rem",
        }}>
          {error}
        </div>
      )}

      <Dialog open={!!editing} onOpenChange={(open) => { if (!open) setEditing(null); }}>
        <DialogContent style={{ maxWidth: 900 }}>
          <DialogHeader>
            <DialogTitle>Edit Skill</DialogTitle>
          </DialogHeader>

          {!editing ? null : !editSchema || !editInitialValues ? (
            <p style={{ color: "var(--text-muted)" }}>Loading…</p>
          ) : (
            <SchemaForm
              schema={editSchema}
              initialValues={editInitialValues as any}
              submitLabel={savingEdit ? "Saving..." : "Save"}
              isLoading={savingEdit}
              onSubmit={async (data: Record<string, FormValue>) => {
                const manifest_json = String(data.manifest_json || "");
                const skill_md = String(data.skill_md || "");
                const secrets = Array.isArray(data.secrets) ? data.secrets : [];

                setSavingEdit(true);
                setError(null);
                try {
                  await skillsApiService.updateSkill(editing.skill_id, editing.version, {
                    manifest_json,
                    skill_md,
                    secrets: secrets as any,
                  });
                  setEditing(null);
                  await load();
                } catch (e) {
                  setError(e instanceof Error ? e.message : "Failed to save skill");
                } finally {
                  setSavingEdit(false);
                }
              }}
            />
          )}
        </DialogContent>
      </Dialog>

      <Card>
        <CardHeader>
          <CardTitle>Uploaded Skills</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p style={{ color: "var(--text-muted)" }}>Loading…</p>
          ) : skills.length === 0 ? (
            <p style={{ color: "var(--text-muted)" }}>No skills uploaded yet.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {skills.map((s) => (
                <div
                  key={`${s.skill_id}:${s.version}`}
                  style={{
                    border: "1px solid var(--border-subtle)",
                    borderRadius: "0.5rem",
                    padding: "0.75rem",
                    display: "flex",
                    justifyContent: "space-between",
                    gap: "1rem",
                    alignItems: "flex-start",
                    backgroundColor: "var(--bg-secondary)",
                  }}
                >
                  <div style={{ flex: 1 }}>
                    <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                      <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{s.name}</span>
                      <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                        {s.skill_id} • v{s.version}
                      </span>
                      <span style={{
                        fontSize: "0.75rem",
                        padding: "0.125rem 0.5rem",
                        borderRadius: "0.25rem",
                        backgroundColor: s.status === "active" ? "rgba(16,185,129,0.12)" : "rgba(148,163,184,0.12)",
                        color: s.status === "active" ? "#10b981" : "var(--text-muted)",
                      }}>
                        {s.status}
                      </span>
                    </div>
                    {s.description && (
                      <p style={{ marginTop: "0.25rem", color: "var(--text-muted)", fontSize: "0.875rem" }}>{s.description}</p>
                    )}
                  </div>

                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <Button variant="outline" onClick={() => void openEdit(s)}>
                      Edit
                    </Button>

                    <Button variant="outline" onClick={() => void toggle(s)}>
                      {s.status === "active" ? (
                        <>
                          <ToggleRight style={{ height: 16, width: 16, marginRight: 8 }} /> Deactivate
                        </>
                      ) : (
                        <>
                          <ToggleLeft style={{ height: 16, width: 16, marginRight: 8 }} /> Activate
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
