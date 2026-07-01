import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Bot, CheckCircle2, ChevronLeft, Download, ShieldCheck } from "lucide-react";

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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../../components/ui";
import { agentMarketplaceApiService } from "../../../services/agentMarketplace";
import { agentApiService } from "../../../services/agents/AgentApiService";
import type {
  ImportMarketplaceAgentRequest,
  MarketplaceAgentDetail,
  MarketplaceImportPlan,
  SkillFormState,
} from "../../../types/agentMarketplace";
import type { FormSchema, FormValue, SelectOption } from "../../../types/form";

export function MarketplaceAgentDetail() {
  const { templateId } = useParams<{ templateId: string }>();
  const navigate = useNavigate();
  const [agent, setAgent] = useState<MarketplaceAgentDetail | null>(null);
  const [plan, setPlan] = useState<MarketplaceImportPlan | null>(null);
  const [createSchema, setCreateSchema] = useState<FormSchema | null>(null);
  const [loading, setLoading] = useState(true);
  const [importOpen, setImportOpen] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [agentName, setAgentName] = useState("");
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [skillFormState, setSkillFormState] = useState<SkillFormState>({});

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!templateId) return;
      setLoading(true);
      setError(null);
      try {
        const [detail, importPlan, schema] = await Promise.all([
          agentMarketplaceApiService.getAgent(templateId),
          agentMarketplaceApiService.getImportPlan(templateId),
          agentApiService.getCreateSchema(),
        ]);
        if (!cancelled) {
          setAgent(detail);
          setPlan(importPlan);
          setCreateSchema(schema);
          setAgentName(importPlan.agent.default_name);
          setProvider(importPlan.agent.default_provider);
          setModel(importPlan.agent.default_model ?? "");
        }
      } catch (err) {
        console.error("Error loading marketplace agent:", err);
        if (!cancelled) setError("Failed to load marketplace agent.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [templateId]);

  const providerOptions = useMemo(() => optionsFor(createSchema, "agent_provider"), [createSchema]);
  const modelOptions = useMemo(() => optionsFor(createSchema, "agent_model"), [createSchema]);

  const handleImport = async () => {
    if (!templateId || !plan) return;
    setImporting(true);
    setError(null);
    try {
      const payload: ImportMarketplaceAgentRequest = {
        agent_name: agentName,
        agent_provider: provider,
        agent_model: model,
        skill_configs: Object.fromEntries(
          Object.entries(skillFormState).map(([key, values]) => [key, stringifyFormValues(values)])
        ),
      };
      const imported = await agentMarketplaceApiService.importAgent(templateId, payload);
      navigate(`/dashboard/agents/${imported.agent_id}`);
    } catch (err) {
      console.error("Error importing marketplace agent:", err);
      setError("Failed to import agent. Check required skill configuration and try again.");
    } finally {
      setImporting(false);
    }
  };

  if (loading) return <LoadingState />;
  if (error && !agent) return <ErrorState message={error} onRetry={() => window.location.reload()} />;
  if (!agent || !plan) return <ErrorState message="Marketplace agent not found." />;

  return (
    <Page>
      <Inline gap="md" wrap={false}>
        <Button variant="ghost" size="icon" onClick={() => navigate("/dashboard/agents/marketplace")}>
          <ChevronLeft className="h-5 w-5" />
        </Button>
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-[var(--gradient-start)] to-[var(--gradient-mid)]">
          <Bot className="h-6 w-6 text-white" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold text-[var(--text-primary)]">{agent.title}</h1>
          <p className="text-sm text-[var(--text-muted)]">by {agent.publisher_display_name} · v{agent.template_version}</p>
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
              <p className="text-sm leading-7 text-[var(--text-secondary)]">{agent.full_description}</p>
              <div className="flex flex-wrap gap-2">
                {agent.tags.map((tag) => (
                  <span key={tag} className="rounded-md bg-[var(--bg-secondary)] px-2.5 py-1 text-xs text-[var(--text-muted)]">
                    {tag}
                  </span>
                ))}
              </div>
              </Stack>
            </PanelBody>
          </Panel>

          <Panel>
            <PanelHeader>
              <PanelTitle>Instructions</PanelTitle>
            </PanelHeader>
            <PanelBody>
              <ReadOnlyContent variant="instructions" selectable={false}>
                {agent.agent_persona}
              </ReadOnlyContent>
            </PanelBody>
          </Panel>
        </Stack>

        <Stack gap="xl">
          <Panel>
            <PanelHeader>
              <PanelTitle>Import</PanelTitle>
            </PanelHeader>
            <PanelBody>
              <Stack gap="md">
              <MetaRow label="Architecture" value={agent.agent_architecture} />
              <MetaRow label="Provider" value={agent.agent_provider} />
              <MetaRow label="Model" value={agent.agent_model || "Default"} />
              <MetaRow label="Imports" value={String(agent.import_count)} />
              <Button className="w-full" onClick={() => setImportOpen(true)}>
                <Download className="h-4 w-4" />
                Import Agent
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
              {agent.skills.length === 0 ? (
                <p className="text-sm text-[var(--text-muted)]">No skills attached.</p>
              ) : (
                agent.skills.map((skill) => (
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
                      <p className="text-sm font-medium text-[var(--text-primary)]">{skill.display_name || skill.skill_id}</p>
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
        <DialogContent
          className="max-h-[88vh] max-w-3xl overflow-y-auto"
        >
          <DialogHeader>
            <DialogTitle>Import {agent.title}</DialogTitle>
            <DialogDescription>
              Create a private copy and provide your own skill configuration.
            </DialogDescription>
          </DialogHeader>

          <DialogBody>
            <DialogSection className="grid md:grid-cols-3" style={{ gap: "var(--space-5)" }}>
              <Stack gap="xs" className="md:col-span-3">
                <Label>Agent name</Label>
                <Input value={agentName} onChange={(event) => setAgentName(event.target.value)} />
              </Stack>
              {plan.agent.allow_model_override && (
                <>
                  <SelectBlock label="Provider" value={provider} options={providerOptions} onChange={setProvider} />
                  <SelectBlock label="Model" value={model} options={modelOptions} onChange={setModel} className="md:col-span-2" />
                </>
              )}
            </DialogSection>

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
                      onSubmit={(values) => {
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
            <Button onClick={handleImport} disabled={importing || !agentName.trim()}>
              {importing ? "Importing..." : "Import Agent"}
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

function SelectBlock({
  label,
  value,
  options,
  onChange,
  className,
}: {
  label: string;
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  className?: string;
}) {
  return (
    <Stack gap="xs" className={className}>
      <Label>{label}</Label>
      <Select value={value || undefined} onValueChange={onChange}>
        <SelectTrigger>
          <SelectValue placeholder={`Select ${label.toLowerCase()}`} />
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Stack>
  );
}

function optionsFor(schema: FormSchema | null, fieldName: string): SelectOption[] {
  const field = schema?.form_inputs.find((item) => item.name === fieldName);
  if (!field) return [];
  if (field.options) return field.options;
  return (field.values || []).map((value) => ({ value, label: value }));
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
