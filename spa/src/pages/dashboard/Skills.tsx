import { useEffect, useState } from "react";
import { Puzzle, ChevronRight } from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { SchemaForm } from "../../components/forms";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../../components/ui/dialog";
import {
  skillsApiService,
  type SkillRegistryEntry,
  type EnabledSkillResponse,
} from "../../services/skills";
import type { FormValue } from "../../types/form";

export function Skills() {
  const [registry, setRegistry] = useState<SkillRegistryEntry[]>([]);
  const [enabled, setEnabled] = useState<EnabledSkillResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedSkill, setSelectedSkill] = useState<SkillRegistryEntry | null>(null);
  const [schema, setSchema] = useState<import("../../types/form").FormSchema | null>(null);
  const [enabling, setEnabling] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [registryData, enabledData] = await Promise.all([
        skillsApiService.listRegistry(),
        skillsApiService.listEnabled(),
      ]);
      setRegistry(registryData);
      setEnabled(enabledData);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load skills");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleSelectSkill = async (skill: SkillRegistryEntry) => {
    setSelectedSkill(skill);
    setSchema(null);
    setError(null);
    if (skill.has_schema) {
      try {
        const formSchema = await skillsApiService.getSchema(skill.skill_id);
        setSchema(formSchema);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load skill schema");
      }
    }
  };

  const handleEnable = async (data: Record<string, FormValue>) => {
    if (!selectedSkill) return;
    setEnabling(true);
    setError(null);
    try {
      const configValues: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(data)) {
        if (value === null || value === undefined || value === "") continue;
        if (value instanceof File || (Array.isArray(value) && value.some((v) => v instanceof File))) {
          continue;
        }
        configValues[key] = value;
      }
      await skillsApiService.enableSkill(selectedSkill.skill_id, configValues);
      setSelectedSkill(null);
      setSchema(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to enable skill");
    } finally {
      setEnabling(false);
    }
  };

  const handleEnableNoSchema = async () => {
    if (!selectedSkill) return;
    setEnabling(true);
    setError(null);
    try {
      await skillsApiService.enableSkill(selectedSkill.skill_id, {});
      setSelectedSkill(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to enable skill");
    } finally {
      setEnabling(false);
    }
  };

  const handleDisable = async (skillId: string) => {
    setError(null);
    try {
      await skillsApiService.disableSkill(skillId);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to disable skill");
    }
  };

  const isEnabled = (skillId: string) => enabled.some((e) => e.skill_id === skillId);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <div>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)" }}>Skills</h1>
        <p style={{ color: "var(--text-muted)", marginTop: "0.25rem" }}>
          Enable skills from the registry. Some skills require configuration before use.
        </p>
      </div>

      {error && (
        <div
          style={{
            padding: "0.75rem 1rem",
            backgroundColor: "rgba(239, 68, 68, 0.1)",
            border: "1px solid rgba(239, 68, 68, 0.3)",
            borderRadius: "0.5rem",
            color: "var(--text-primary)",
          }}
        >
          {error}
        </div>
      )}

      {loading ? (
        <p style={{ color: "var(--text-muted)" }}>Loading skills...</p>
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Available Skills</CardTitle>
              <CardDescription>Select a skill to enable it. Skills with configuration will show a form.</CardDescription>
            </CardHeader>
            <CardContent>
              {registry.length === 0 ? (
                <p style={{ color: "var(--text-muted)" }}>No skills found in the registry.</p>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  {registry.map((skill) => (
                    <div
                      key={skill.skill_id}
                      onClick={() => handleSelectSkill(skill)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => e.key === "Enter" && handleSelectSkill(skill)}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        padding: "0.75rem 1rem",
                        backgroundColor: "rgba(255,255,255,0.02)",
                        border: "1px solid var(--border-subtle)",
                        borderRadius: "0.5rem",
                        cursor: "pointer",
                        transition: "background-color 0.15s",
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.05)";
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.02)";
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                        <Puzzle className="h-5 w-5 text-[var(--text-muted)]" />
                        <div>
                          <div style={{ fontWeight: 500, color: "var(--text-primary)" }}>{skill.name}</div>
                          {skill.description && (
                            <div style={{ fontSize: "0.875rem", color: "var(--text-muted)", marginTop: "0.125rem" }}>
                              {skill.description}
                            </div>
                          )}
                        </div>
                        {isEnabled(skill.skill_id) && (
                          <span
                            style={{
                              fontSize: "0.75rem",
                              padding: "0.125rem 0.5rem",
                              backgroundColor: "rgba(34, 197, 94, 0.2)",
                              color: "rgb(34, 197, 94)",
                              borderRadius: "0.25rem",
                            }}
                          >
                            Enabled
                          </span>
                        )}
                      </div>
                      <ChevronRight className="h-5 w-5 text-[var(--text-muted)]" />
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {enabled.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Enabled Skills</CardTitle>
                <CardDescription>Skills you have enabled. Disable to remove stored configuration.</CardDescription>
              </CardHeader>
              <CardContent>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  {enabled.map((e) => (
                    <div
                      key={e.skill_id}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        padding: "0.75rem 1rem",
                        backgroundColor: "rgba(255,255,255,0.02)",
                        border: "1px solid var(--border-subtle)",
                        borderRadius: "0.5rem",
                      }}
                    >
                      <span style={{ fontWeight: 500, color: "var(--text-primary)" }}>{e.skill_id}</span>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleDisable(e.skill_id)}
                        style={{ color: "var(--destructive)" }}
                      >
                        Disable
                      </Button>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {/* Enable dialog */}
      <Dialog open={selectedSkill !== null} onOpenChange={(open) => !open && setSelectedSkill(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{selectedSkill ? `${selectedSkill.name} - Enable` : ""}</DialogTitle>
          </DialogHeader>
          {selectedSkill && (
            <div style={{ padding: "1rem 0" }}>
              {selectedSkill.has_schema ? (
                schema ? (
                  <SchemaForm
                    schema={schema}
                    onSubmit={handleEnable}
                    submitLabel={enabling ? "Enabling..." : "Enable"}
                    cancelLabel="Cancel"
                    isLoading={enabling}
                    onCancel={() => setSelectedSkill(null)}
                  />
                ) : (
                  <p style={{ color: "var(--text-muted)" }}>Loading form...</p>
                )
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                  <p style={{ color: "var(--text-muted)" }}>
                    This skill does not require any configuration. Click Enable to activate it.
                  </p>
                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <Button onClick={handleEnableNoSchema} disabled={enabling}>
                      {enabling ? "Enabling..." : "Enable"}
                    </Button>
                    <Button variant="outline" onClick={() => setSelectedSkill(null)} disabled={enabling}>
                      Cancel
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
