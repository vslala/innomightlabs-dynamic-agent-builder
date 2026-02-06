import { useEffect, useState } from "react";
import { ToggleLeft, ToggleRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { SchemaForm } from "../../components/forms";
import { skillsApiService, type SkillDefinitionResponse } from "../../services/skills";
import type { FormSchema, FormValue } from "../../types/form";

export function Skills() {
  const [skills, setSkills] = useState<SkillDefinitionResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadSchema, setUploadSchema] = useState<FormSchema | null>(null);

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
      } catch (e) {
        console.error("Failed to load skills upload schema", e);
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

      <Card>
        <CardHeader>
          <CardTitle>Upload Skill</CardTitle>
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
                  ? fileValue[0]
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
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
