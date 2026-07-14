import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  CheckCircle2,
  ChevronLeft,
  Download,
  GitBranch,
  ShieldCheck,
  Workflow,
} from "lucide-react";

import { SchemaForm } from "../../../components/forms";
import { Inline, Page, PageBody, Stack } from "../../../components/layout";
import {
  Button,
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogSection,
  DialogTitle,
  ErrorState,
  Input,
  Label,
  LoadingState,
  Panel,
  PanelBody,
  PanelHeader,
  PanelTitle,
  ReadOnlyContent,
  Textarea,
} from "../../../components/ui";
import { automationMarketplaceApiService } from "../../../services/automationMarketplace";
import { HttpError } from "../../../services/http/client";
import type {
  AutomationMarketplaceFormState,
  ImportMarketplaceAutomationRequest,
  MarketplaceAutomationDetail,
  MarketplaceAutomationImportPlan,
} from "../../../types/automationMarketplace";
import type { FormValue } from "../../../types/form";

export function AutomationMarketplaceDetail() {
  const { templateId } = useParams<{ templateId: string }>();
  const navigate = useNavigate();
  const [automation, setAutomation] = useState<MarketplaceAutomationDetail | null>(null);
  const [plan, setPlan] = useState<MarketplaceAutomationImportPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [importOpen, setImportOpen] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [skillFormState, setSkillFormState] = useState<AutomationMarketplaceFormState>({});
  const [inputFormState, setInputFormState] = useState<Record<string, FormValue>>({});
  const [importSessionId, setImportSessionId] = useState<string | null>(null);
  const [savingSection, setSavingSection] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!templateId) return;
      setLoading(true);
      setError(null);
      try {
        const [detail, importPlan] = await Promise.all([
          automationMarketplaceApiService.getAutomation(templateId),
          automationMarketplaceApiService.getImportPlan(templateId),
        ]);
        if (!cancelled) {
          setAutomation(detail);
          setPlan(importPlan);
          setTitle(importPlan.automation.default_title);
          setDescription(importPlan.automation.description ?? "");
        }
      } catch (err) {
        console.error("Error loading marketplace automation:", err);
        if (!cancelled) setError("Failed to load marketplace automation.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [templateId]);

  const handleImport = async () => {
    if (!templateId || !plan) return;
    setImporting(true);
    setError(null);
    try {
      const payload: ImportMarketplaceAutomationRequest = {
        session_id: importSessionId,
        title,
        description: description.trim() || null,
        skill_configs: Object.fromEntries(
          Object.entries(skillFormState).map(([key, values]) => [key, stringifyFormValues(values)])
        ),
        import_inputs: normalizeImportInputs(inputFormState),
      };
      const imported = await automationMarketplaceApiService.importAutomation(templateId, payload);
      navigate(`/dashboard/automations/${imported.automation_id}`);
    } catch (err) {
      console.error("Error importing marketplace automation:", err);
      setError(errorMessage(err, "Failed to import automation. Check required configuration and try again."));
    } finally {
      setImporting(false);
    }
  };

  const saveImportSession = async (
    sectionKey: string,
    payload: {
      skill_configs?: Record<string, Record<string, string>>;
      import_inputs?: Record<string, string | Record<string, string>>;
    } = {}
  ) => {
    if (!templateId) return;
    setSavingSection(sectionKey);
    setError(null);
    try {
      const saved = await automationMarketplaceApiService.saveImportSession(templateId, {
        session_id: importSessionId,
        title,
        description: description.trim() || null,
        ...payload,
      });
      setImportSessionId(saved.session_id);
    } catch (err) {
      console.error("Error saving marketplace automation import session:", err);
      setError(errorMessage(err, "Failed to save import configuration."));
      throw err;
    } finally {
      setSavingSection(null);
    }
  };

  if (loading) return <LoadingState />;
  if (error && !automation) return <ErrorState message={error} onRetry={() => window.location.reload()} />;
  if (!automation || !plan) return <ErrorState message="Marketplace automation not found." />;

  return (
    <Page>
      <Inline gap="md" wrap={false}>
        <Button variant="ghost" size="icon" onClick={() => navigate("/dashboard/automations/marketplace")}>
          <ChevronLeft className="h-5 w-5" />
        </Button>
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-[var(--gradient-start)] to-[var(--gradient-mid)]">
          <Workflow className="h-6 w-6 text-white" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold text-[var(--text-primary)]">{automation.title}</h1>
          <p className="text-sm text-[var(--text-muted)]">
            by {automation.publisher_display_name} · v{automation.template_version}
          </p>
        </div>
      </Inline>

      {error && (
        <div
          className="rounded-lg border border-red-500/20 bg-red-500/10 text-sm text-red-400"
          style={{ padding: "0.875rem 1rem" }}
        >
          {error}
        </div>
      )}

      <PageBody className="grid xl:grid-cols-[minmax(0,1fr)_22rem]" style={{ gap: "var(--space-8)" }}>
        <Stack gap="xl">
          <Panel>
            <PanelHeader>
              <PanelTitle>Overview</PanelTitle>
            </PanelHeader>
            <PanelBody>
              <Stack gap="md">
                <p className="text-sm leading-7 text-[var(--text-secondary)]">
                  {automation.full_description}
                </p>
                {automation.tags.length > 0 ? (
                  <Inline gap="xs">
                    {automation.tags.map((tag) => (
                      <span
                        key={tag}
                        className="rounded-md bg-[var(--bg-secondary)] px-2.5 py-1 text-xs text-[var(--text-muted)]"
                      >
                        {tag}
                      </span>
                    ))}
                  </Inline>
                ) : null}
              </Stack>
            </PanelBody>
          </Panel>

          <Panel>
            <PanelHeader>
              <PanelTitle>Workflow</PanelTitle>
            </PanelHeader>
            <PanelBody>
              <Stack gap="md">
                {automation.nodes.map((node) => (
                  <div
                    key={node.node_id}
                    className="rounded-lg border border-[var(--border-default)]"
                    style={{ padding: "0.875rem 1rem" }}
                  >
                    <Inline gap="sm" wrap={false}>
                      <GitBranch className="h-4 w-4 text-[var(--gradient-start)]" />
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-[var(--text-primary)]">
                          {node.name}
                        </p>
                        <p className="text-xs text-[var(--text-muted)]">{node.type}</p>
                      </div>
                    </Inline>
                    {node.description ? (
                      <p className="mt-2 text-xs leading-5 text-[var(--text-muted)]">
                        {node.description}
                      </p>
                    ) : null}
                  </div>
                ))}
              </Stack>
            </PanelBody>
          </Panel>

          {automation.import_inputs.length > 0 ? (
            <Panel>
              <PanelHeader>
                <PanelTitle>Required Inputs</PanelTitle>
              </PanelHeader>
              <PanelBody>
                <ReadOnlyContent selectable={false}>
                  {automation.import_inputs
                    .map((input) => `- ${input.label}${input.required ? " (required)" : ""}`)
                    .join("\n")}
                </ReadOnlyContent>
              </PanelBody>
            </Panel>
          ) : null}
        </Stack>

        <Stack gap="xl">
          <Panel>
            <PanelHeader>
              <PanelTitle>Import</PanelTitle>
            </PanelHeader>
            <PanelBody>
              <Stack gap="md">
                <MetaRow label="Nodes" value={String(automation.node_count)} />
                <MetaRow label="Edges" value={String(automation.edge_count)} />
                <MetaRow label="Skills" value={String(automation.skill_count)} />
                <MetaRow label="Imports" value={String(automation.import_count)} />
                <Button className="w-full" onClick={() => setImportOpen(true)}>
                  <Download className="h-4 w-4" />
                  Import Automation
                </Button>
              </Stack>
            </PanelBody>
          </Panel>

          <Panel>
            <PanelHeader>
              <PanelTitle>Skills</PanelTitle>
            </PanelHeader>
            <PanelBody>
              <Stack gap="sm">
                {automation.skills.length === 0 ? (
                  <p className="text-sm text-[var(--text-muted)]">No skills attached.</p>
                ) : (
                  automation.skills.map((skill) => (
                    <div
                      key={skill.template_skill_key}
                      className="rounded-lg border border-[var(--border-default)]"
                      style={{ padding: "0.875rem 1rem" }}
                    >
                      <div className="flex items-center gap-2">
                        {skill.enabled_on_import ? (
                          <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                        ) : (
                          <ShieldCheck className="h-4 w-4 text-amber-400" />
                        )}
                        <p className="text-sm font-medium text-[var(--text-primary)]">
                          {skill.display_name || skill.skill_id}
                        </p>
                      </div>
                      <p className="mt-1 text-xs leading-5 text-[var(--text-muted)]">
                        {skill.description || "Configured during import."}
                      </p>
                    </div>
                  ))
                )}
              </Stack>
            </PanelBody>
          </Panel>
        </Stack>
      </PageBody>

      <Dialog open={importOpen} onOpenChange={setImportOpen}>
        <DialogContent className="max-h-[88vh] max-w-3xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Import {automation.title}</DialogTitle>
            <DialogDescription>
              Create a private workflow copy and provide your own required configuration.
            </DialogDescription>
          </DialogHeader>

          <DialogBody>
            <DialogSection>
              <Stack gap="md">
                <Stack gap="xs">
                  <Label>Automation title</Label>
                  <Input value={title} onChange={(event) => setTitle(event.target.value)} />
                </Stack>
                <Stack gap="xs">
                  <Label>Description</Label>
                  <Textarea
                    value={description}
                    onChange={(event) => setDescription(event.target.value)}
                    rows={4}
                  />
                </Stack>
              </Stack>
            </DialogSection>

            {plan.input_form.form_inputs.length > 0 ? (
              <Panel>
                <PanelHeader>
                  <PanelTitle>{plan.input_form.form_name}</PanelTitle>
                </PanelHeader>
                <PanelBody>
                  <SchemaForm
                    schema={plan.input_form}
                    submitLabel="Save Inputs"
                    isLoading={savingSection === "inputs"}
                    onSubmit={async (values) => {
                      const normalized = normalizeImportInputs(values);
                      await saveImportSession("inputs", { import_inputs: normalized });
                      setInputFormState(values);
                    }}
                  />
                </PanelBody>
              </Panel>
            ) : null}

            {plan.skill_forms.map((skillForm) => (
              <Panel key={skillForm.template_skill_key}>
                <PanelHeader>
                  <PanelTitle>{skillForm.skill_name}</PanelTitle>
                </PanelHeader>
                <PanelBody>
                  {skillForm.form.form_inputs.length === 0 ? (
                    <p className="text-sm text-[var(--text-muted)]">No configuration required.</p>
                  ) : (
                    <SchemaForm
                      schema={skillForm.form}
                      submitLabel="Save Skill Config"
                      isLoading={savingSection === skillForm.template_skill_key}
                      onSubmit={async (values) => {
                        const stringified = stringifyFormValues(values);
                        await saveImportSession(skillForm.template_skill_key, {
                          skill_configs: {
                            [skillForm.template_skill_key]: stringified,
                          },
                        });
                        setSkillFormState((current) => ({
                          ...current,
                          [skillForm.template_skill_key]: values,
                        }));
                      }}
                    />
                  )}
                </PanelBody>
              </Panel>
            ))}
          </DialogBody>

          <DialogFooter>
            <Button variant="outline" onClick={() => setImportOpen(false)} disabled={importing}>
              Cancel
            </Button>
            <Button onClick={handleImport} disabled={importing || !title.trim()}>
              {importing ? "Importing..." : "Import Automation"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Page>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div
      className="flex items-center justify-between gap-4 border-b border-[var(--border-default)] last:border-b-0"
      style={{ paddingBottom: "0.875rem" }}
    >
      <span className="text-sm text-[var(--text-muted)]">{label}</span>
      <span className="text-right text-sm font-medium text-[var(--text-primary)]">{value}</span>
    </div>
  );
}

function stringifyFormValues(values: Record<string, FormValue>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(values).map(([key, value]) => [key, stringifyFormValue(value)])
  );
}

function stringifyFormValue(value: FormValue): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return "";
  if (value instanceof FileList) return "";
  return JSON.stringify(value);
}

function normalizeImportInputs(values: Record<string, FormValue>): Record<string, string | Record<string, string>> {
  return Object.fromEntries(
    Object.entries(values).map(([key, value]) => [key, normalizeImportInput(value)])
  );
}

function normalizeImportInput(value: FormValue): string | Record<string, string> {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return "";
  if (value instanceof FileList) return "";
  return value;
}

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof HttpError && typeof error.message === "string" && error.message.trim()) {
    return error.message;
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
}
