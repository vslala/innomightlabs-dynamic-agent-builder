import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronLeft, Share2, Workflow } from "lucide-react";
import { Link, Outlet, useNavigate, useParams } from "react-router-dom";

import {
  Button,
  Card,
  CardContent,
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogSection,
  DialogTitle,
  Input,
  Label,
  Textarea,
} from "../../../components/ui";
import { StatusBadge } from "../../../components/ui/status-badge";
import { FieldGroup, Inline, Stack } from "../../../components/layout";
import { automationApiService } from "../../../services/automations";
import { automationMarketplaceApiService } from "../../../services/automationMarketplace";
import type {
  AutomationGraphResponse,
  AutomationResponse,
  AutomationSkillResponse,
} from "../../../types/automation";
import type { MarketplaceAutomationImportInput } from "../../../types/automationMarketplace";
import { AutomationSideNav } from "./components/AutomationSideNav";

function toBadgeStatus(status: AutomationResponse["status"]) {
  return status === "active" ? "active" : "inactive";
}

export function AutomationDetailLayout() {
  const { automationId } = useParams<{ automationId: string }>();
  const navigate = useNavigate();
  const [automation, setAutomation] = useState<AutomationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [publishOpen, setPublishOpen] = useState(false);
  const [publishGraph, setPublishGraph] = useState<AutomationGraphResponse | null>(null);
  const [publishSkills, setPublishSkills] = useState<AutomationSkillResponse[]>([]);
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  const [selectedEdgeIds, setSelectedEdgeIds] = useState<string[]>([]);
  const [selectedSkillIds, setSelectedSkillIds] = useState<string[]>([]);
  const [publishTitle, setPublishTitle] = useState("");
  const [publishShortDescription, setPublishShortDescription] = useState("");
  const [publishFullDescription, setPublishFullDescription] = useState("");
  const [publishTags, setPublishTags] = useState("");
  const [publishInputs, setPublishInputs] = useState<MarketplaceAutomationImportInput[]>([]);
  const [publishError, setPublishError] = useState<string | null>(null);
  const [publishing, setPublishing] = useState(false);

  const loadAutomation = useCallback(async () => {
    if (!automationId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await automationApiService.getAutomation(automationId);
      setAutomation(data);
    } catch (err) {
      console.error("Error loading automation:", err);
      setError("Failed to load automation. It may not exist or you don't have access.");
      setAutomation(null);
    } finally {
      setLoading(false);
    }
  }, [automationId]);

  useEffect(() => {
    void loadAutomation();
  }, [loadAutomation]);

  const detectedInputKeys = useMemo(
    () => detectSelectedInputPlaceholders(publishGraph, selectedNodeIds),
    [publishGraph, selectedNodeIds]
  );
  const missingDetectedInputKeys = useMemo(() => {
    const declared = new Set(publishInputs.map((input) => input.input_key));
    return detectedInputKeys.filter((key) => !declared.has(key));
  }, [detectedInputKeys, publishInputs]);

  const openPublishDialog = async () => {
    if (!automationId || !automation) return;
    setPublishOpen(true);
    setPublishError(null);
    setPublishTitle(automation.title);
    setPublishShortDescription(automation.description || "");
    setPublishFullDescription(automation.description || "");
    setPublishTags("");
    setPublishInputs([]);
    try {
      const [graph, skills] = await Promise.all([
        automationApiService.getGraph(automationId),
        automationApiService.listSkills(automationId),
      ]);
      setPublishGraph(graph);
      setPublishSkills(skills);
      setSelectedNodeIds(graph.nodes.map((node) => node.node_id));
      setSelectedEdgeIds(graph.edges.map((edge) => edge.edge_id));
      setSelectedSkillIds(skills.map((skill) => skill.installed_skill_id || skill.skill_id));
      setPublishInputs(detectSelectedInputPlaceholders(graph, graph.nodes.map((node) => node.node_id)).map(createImportInput));
    } catch (err) {
      console.error("Error loading automation publish plan:", err);
      setPublishError("Failed to load workflow details for publishing.");
    }
  };

  const handlePublish = async () => {
    if (!automationId) return;
    setPublishing(true);
    setPublishError(null);
    try {
      const importInputs = mergeDetectedImportInputs(publishInputs, detectedInputKeys);
      await automationMarketplaceApiService.publishAutomation({
        automation_id: automationId,
        title: publishTitle.trim(),
        short_description: publishShortDescription.trim(),
        full_description: publishFullDescription.trim(),
        tags: parseTags(publishTags),
        included_node_ids: publishGraph?.nodes.map((node) => node.node_id) ?? selectedNodeIds,
        included_edge_ids: publishGraph?.edges.map((edge) => edge.edge_id) ?? selectedEdgeIds,
        included_skill_ids: selectedSkillIds,
        import_inputs: importInputs.filter((input) => input.input_key.trim() && input.label.trim()),
        status: "published",
      });
      setPublishOpen(false);
      navigate("/dashboard/automations/marketplace");
    } catch (err) {
      console.error("Error publishing automation:", err);
      setPublishError(errorMessage(err));
    } finally {
      setPublishing(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--gradient-start)] border-t-transparent" />
      </div>
    );
  }

  if (error || !automation) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => navigate("/dashboard/automations")}>
            <ChevronLeft className="h-5 w-5" />
          </Button>
          <h1 className="text-xl font-semibold text-[var(--text-primary)]">Automation Not Found</h1>
        </div>
        <Card>
          <CardContent className="p-12">
            <div className="text-center">
              <Workflow className="h-16 w-16 mx-auto text-[var(--text-muted)] mb-4" />
              <p className="text-[var(--text-muted)] mb-6">{error ?? "Failed to load automation."}</p>
              <Button onClick={() => navigate("/dashboard/automations")}>Back to Automations</Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "2rem" }}>
      <div className="flex items-center justify-between gap-6">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" asChild>
            <Link to="/dashboard/automations">
              <ChevronLeft className="h-5 w-5" />
            </Link>
          </Button>
          <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-[var(--gradient-start)] to-[var(--gradient-mid)] flex items-center justify-center">
            <Workflow className="h-6 w-6 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-xl font-semibold text-[var(--text-primary)]">{automation.title}</h1>
              <StatusBadge status={toBadgeStatus(automation.status)} label={automation.status} />
            </div>
            <p className="text-sm text-[var(--text-muted)]">
              {automation.description || "Automation workflow"}
            </p>
          </div>
        </div>
        <Button variant="outline" onClick={openPublishDialog}>
          <Share2 className="h-4 w-4" />
          Publish
        </Button>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "15rem minmax(0, 1fr)",
          gap: "2rem",
          alignItems: "start",
        }}
      >
        <AutomationSideNav />
        <div style={{ minWidth: 0 }}>
          <Outlet context={{ automation, reloadAutomation: loadAutomation }} />
        </div>
      </div>

      <Dialog open={publishOpen} onOpenChange={setPublishOpen}>
        <DialogContent className="max-h-[88vh] max-w-4xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Publish to Automation Marketplace</DialogTitle>
            <DialogDescription>
              Create a reusable workflow template. Triggers are not published, and skill secrets are never copied.
            </DialogDescription>
          </DialogHeader>

          <DialogBody>
            {publishError ? (
              <div
                className="rounded-lg border border-red-500/20 bg-red-500/10 text-sm text-red-400"
                style={{ padding: "0.875rem 1rem" }}
              >
                {publishError}
              </div>
            ) : null}

            <DialogSection>
              <Stack gap="md">
                <FieldGroup>
                  <Label>Title</Label>
                  <Input value={publishTitle} onChange={(event) => setPublishTitle(event.target.value)} />
                </FieldGroup>
                <FieldGroup>
                  <Label>Short description</Label>
                  <Input
                    value={publishShortDescription}
                    onChange={(event) => setPublishShortDescription(event.target.value)}
                  />
                </FieldGroup>
                <FieldGroup>
                  <Label>Full description</Label>
                  <Textarea
                    rows={5}
                    value={publishFullDescription}
                    onChange={(event) => setPublishFullDescription(event.target.value)}
                  />
                </FieldGroup>
                <FieldGroup>
                  <Label>Tags</Label>
                  <Input
                    value={publishTags}
                    onChange={(event) => setPublishTags(event.target.value)}
                    placeholder="reports, productivity, league-of-legends"
                  />
                </FieldGroup>
              </Stack>
            </DialogSection>

            <DialogSection>
              <Stack gap="md">
                <h3 className="text-sm font-semibold text-[var(--text-primary)]">Workflow Items</h3>
                <SelectionList
                  title="Nodes"
                  items={publishGraph?.nodes ?? []}
                  selectedIds={selectedNodeIds}
                  idFor={(node) => node.node_id}
                  labelFor={(node) => node.name}
                  descriptionFor={(node) => node.type}
                  onChange={setSelectedNodeIds}
                  locked
                />
                <SelectionList
                  title="Edges"
                  items={publishGraph?.edges ?? []}
                  selectedIds={selectedEdgeIds}
                  idFor={(edge) => edge.edge_id}
                  labelFor={(edge) => `${edge.source_node_id} -> ${edge.target_node_id}`}
                  descriptionFor={(edge) => edge.label}
                  onChange={setSelectedEdgeIds}
                  locked
                />
                <SelectionList
                  title="Skills"
                  items={publishSkills}
                  selectedIds={selectedSkillIds}
                  idFor={(skill) => skill.installed_skill_id || skill.skill_id}
                  labelFor={(skill) => skill.name}
                  descriptionFor={(skill) => skill.skill_id}
                  onChange={setSelectedSkillIds}
                />
              </Stack>
            </DialogSection>

            <DialogSection>
              <Stack gap="md">
                <Inline justify="space-between">
                  <h3 className="text-sm font-semibold text-[var(--text-primary)]">Import Inputs</h3>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      setPublishInputs((current) => [
                        ...current,
                        createImportInput(`input_${current.length + 1}`),
                      ])
                    }
                  >
                    Add Input
                  </Button>
                </Inline>
                {detectedInputKeys.length > 0 ? (
                  <div
                    className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)]"
                    style={{ padding: "0.875rem 1rem" }}
                  >
                    <Stack gap="sm">
                      <p className="text-sm font-medium text-[var(--text-primary)]">
                        Detected variables from selected steps
                      </p>
                      <Inline gap="xs">
                        {detectedInputKeys.map((key) => (
                          <span
                            key={key}
                            className="rounded-md bg-[var(--bg-tertiary)] px-2.5 py-1 text-xs text-[var(--text-secondary)]"
                          >
                            {`{{ inputs.${key} }}`}
                          </span>
                        ))}
                      </Inline>
                      {missingDetectedInputKeys.length > 0 ? (
                        <Inline justify="space-between" align="center">
                          <p className="text-xs text-amber-300">
                            {missingDetectedInputKeys.length} detected variable
                            {missingDetectedInputKeys.length === 1 ? "" : "s"} still need import fields.
                          </p>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() =>
                              setPublishInputs((current) =>
                                mergeDetectedImportInputs(current, detectedInputKeys)
                              )
                            }
                          >
                            Add Missing
                          </Button>
                        </Inline>
                      ) : null}
                    </Stack>
                  </div>
                ) : (
                  <p className="text-sm text-[var(--text-muted)]">
                    No input placeholders were detected in the selected steps.
                  </p>
                )}
                {publishInputs.length === 0 ? (
                  <p className="text-sm text-[var(--text-muted)]">
                    Add inputs for placeholders such as {"{{ inputs.customer_email }}"} that should be filled during import.
                  </p>
                ) : (
                  <Stack gap="sm">
                    {publishInputs.map((input, index) => (
                      <div
                        key={`${input.input_key}-${index}`}
                        className="rounded-lg border border-[var(--border-default)]"
                        style={{ padding: "0.875rem 1rem" }}
                      >
                        <Inline gap="sm" align="stretch">
                          <Input
                            value={input.input_key}
                            onChange={(event) =>
                              updatePublishInput(setPublishInputs, index, "input_key", event.target.value)
                            }
                            placeholder="customer_email"
                          />
                          <Input
                            value={input.label}
                            onChange={(event) =>
                              updatePublishInput(setPublishInputs, index, "label", event.target.value)
                            }
                            placeholder="Customer email"
                          />
                          <Button
                            type="button"
                            variant="outline"
                            onClick={() =>
                              setPublishInputs((current) => current.filter((_, itemIndex) => itemIndex !== index))
                            }
                          >
                            Remove
                          </Button>
                        </Inline>
                      </div>
                    ))}
                  </Stack>
                )}
              </Stack>
            </DialogSection>
          </DialogBody>

          <DialogFooter>
            <Button variant="outline" onClick={() => setPublishOpen(false)} disabled={publishing}>
              Cancel
            </Button>
            <Button
              onClick={handlePublish}
              disabled={publishing || !publishTitle.trim() || !publishShortDescription.trim() || !publishFullDescription.trim()}
            >
              {publishing ? "Publishing..." : "Publish"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function SelectionList<T>({
  title,
  items,
  selectedIds,
  idFor,
  labelFor,
  descriptionFor,
  onChange,
  locked = false,
}: {
  title: string;
  items: T[];
  selectedIds: string[];
  idFor: (item: T) => string;
  labelFor: (item: T) => string;
  descriptionFor: (item: T) => string;
  onChange: (ids: string[]) => void;
  locked?: boolean;
}) {
  return (
    <Stack gap="sm">
      <p className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">{title}</p>
      {items.length === 0 ? (
        <p className="text-sm text-[var(--text-muted)]">No {title.toLowerCase()} available.</p>
      ) : (
        <div className="grid gap-2 md:grid-cols-2">
          {items.map((item) => {
            const id = idFor(item);
            const selected = selectedIds.includes(id);
            return (
              <label
                key={id}
                className={`flex items-start gap-3 rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)] ${
                  locked ? "cursor-not-allowed opacity-80" : "cursor-pointer"
                }`}
                style={{ padding: "0.875rem 1rem" }}
              >
                <input
                  type="checkbox"
                  checked={selected}
                  disabled={locked}
                  onChange={(event) => {
                    if (locked) return;
                    if (event.target.checked) {
                      onChange([...selectedIds, id]);
                    } else {
                      onChange(selectedIds.filter((value) => value !== id));
                    }
                  }}
                />
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium text-[var(--text-primary)]">
                    {labelFor(item)}
                  </span>
                  <span className="block truncate text-xs text-[var(--text-muted)]">
                    {descriptionFor(item)}
                  </span>
                </span>
              </label>
            );
          })}
        </div>
      )}
    </Stack>
  );
}

function createImportInput(inputKey: string): MarketplaceAutomationImportInput {
  return {
    input_key: inputKey,
    label: humanizeInputKey(inputKey),
    description: null,
    required: true,
    form_input: {
      input_type: "text",
      name: inputKey,
      label: humanizeInputKey(inputKey),
      attr: {
        smart_values: "true",
      },
    },
  };
}

function updatePublishInput(
  setPublishInputs: React.Dispatch<React.SetStateAction<MarketplaceAutomationImportInput[]>>,
  index: number,
  field: "input_key" | "label",
  value: string
) {
  setPublishInputs((current) =>
    current.map((input, itemIndex) => {
      if (itemIndex !== index) return input;
      const next = { ...input, [field]: value };
      return {
        ...next,
        form_input: {
          ...next.form_input,
          name: next.input_key,
          label: next.label,
        },
      };
    })
  );
}

function parseTags(value: string): string[] {
  return value
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
}

function detectSelectedInputPlaceholders(
  graph: AutomationGraphResponse | null,
  selectedNodeIds: string[]
): string[] {
  if (!graph) return [];
  const selected = new Set(selectedNodeIds);
  const keys = new Set<string>();
  graph.nodes
    .filter((node) => selected.has(node.node_id))
    .forEach((node) => collectInputPlaceholders(node.config, keys));
  return [...keys].sort();
}

function collectInputPlaceholders(value: unknown, keys: Set<string>) {
  if (typeof value === "string") {
    const pattern = /{{\s*inputs\.([a-zA-Z0-9_-]+)\s*}}/g;
    for (const match of value.matchAll(pattern)) {
      keys.add(match[1]);
    }
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item) => collectInputPlaceholders(item, keys));
    return;
  }
  if (value && typeof value === "object") {
    Object.values(value).forEach((item) => collectInputPlaceholders(item, keys));
  }
}

function mergeDetectedImportInputs(
  current: MarketplaceAutomationImportInput[],
  detectedKeys: string[]
): MarketplaceAutomationImportInput[] {
  const existing = new Set(current.map((input) => input.input_key));
  return [
    ...current,
    ...detectedKeys.filter((key) => !existing.has(key)).map(createImportInput),
  ];
}

function humanizeInputKey(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "Failed to publish automation. Check selected items and import input placeholders.";
}
