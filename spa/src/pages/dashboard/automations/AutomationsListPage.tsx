import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { CalendarClock, GitBranch, Plus, Settings, ShoppingBag, Trash2, Workflow, type LucideIcon } from "lucide-react";
import "./AutomationsListPage.css";

import {
  Button,
  Card,
  CardContent,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  EmptyState,
  ErrorState,
  Input,
  Label,
  LoadingState,
  StatusBadge,
  Textarea,
} from "../../../components/ui";
import { FieldGroup, Page, PageBody, PageTitle, Stack } from "../../../components/layout";
import { automationApiService } from "../../../services/automations";
import type { AutomationResponse, AutomationStatus } from "../../../types/automation";

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

function badgeStatus(status: AutomationResponse["status"]) {
  if (status === "active") return "active";
  if (status === "draft") return "draft";
  return "inactive";
}

function statusLabel(status: AutomationStatus): string {
  if (status === "active") return "Active";
  if (status === "draft") return "Draft";
  if (status === "disabled") return "Disabled";
  return status;
}

export function AutomationsListPage() {
  const navigate = useNavigate();
  const [automations, setAutomations] = useState<AutomationResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selectedAutomation, setSelectedAutomation] = useState<AutomationResponse | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const loadAutomations = async () => {
    try {
      setError(null);
      const data = await automationApiService.listAutomations();
      setAutomations(data.filter((automation) => automation.status !== "deleted"));
    } catch (err) {
      console.error("Error loading automations:", err);
      setError("Failed to load automations. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadAutomations();
  }, []);

  const handleCreate = async () => {
    if (!title.trim()) return;
    setSaving(true);
    try {
      const graph = await automationApiService.createAutomation({
        title: title.trim(),
        description: description.trim() || null,
        status: "draft",
      });
      setCreateOpen(false);
      setTitle("");
      setDescription("");
      navigate(`/dashboard/automations/${graph.automation.automation_id}`);
    } catch (err) {
      console.error("Error creating automation:", err);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedAutomation) return;
    setDeleting(true);
    try {
      await automationApiService.deleteAutomation(selectedAutomation.automation_id);
      setDeleteOpen(false);
      setSelectedAutomation(null);
      await loadAutomations();
    } catch (err) {
      console.error("Error deleting automation:", err);
    } finally {
      setDeleting(false);
    }
  };

  if (loading) {
    return <LoadingState />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={loadAutomations} />;
  }

  const activeCount = automations.filter((automation) => automation.status === "active").length;
  const draftCount = automations.filter((automation) => automation.status === "draft").length;
  const disabledCount = automations.filter((automation) => automation.status === "disabled").length;
  const recentlyUpdatedCount = automations.filter((automation) => {
    const updatedAt = new Date(automation.updated_at ?? automation.created_at).getTime();
    return Number.isFinite(updatedAt) && Date.now() - updatedAt < 7 * 24 * 60 * 60 * 1000;
  }).length;

  return (
    <Page className="automations-page">
      <section className="automations-hero">
        <div className="automations-hero__copy">
          <span className="automations-hero__eyebrow">Automation workspace</span>
          <PageTitle>Build repeatable agent workflows</PageTitle>
          <p>
            Chain agent calls, skill actions, schedules, and run history into workflows that are easy to test,
            publish, and reuse.
          </p>
        </div>
        <div className="automations-hero__actions">
          <Button variant="outline" onClick={() => navigate("/dashboard/automations/marketplace")}>
            <ShoppingBag />
            Marketplace
          </Button>
          <Button onClick={() => setCreateOpen(true)}>
            <Plus />
            New automation
          </Button>
        </div>
      </section>

      <PageBody>
        <section className="automations-metrics" aria-label="Automation metrics">
          <MetricCard label="Total" value={automations.length} detail="Reusable workflows" icon={Workflow} />
          <MetricCard label="Active" value={activeCount} detail="Available to run" icon={CalendarClock} />
          <MetricCard label="Draft" value={draftCount} detail="Needs review" icon={GitBranch} />
          <MetricCard label="Updated" value={recentlyUpdatedCount} detail="Changed this week" icon={Settings} />
        </section>

        <div className="automations-layout">
          <Card className="automations-list-card">
            <CardContent className="automations-list-card__content">
              <div className="automations-section-header">
                <div>
                  <h2>Automations</h2>
                  <p>{disabledCount} disabled, {draftCount} draft, {activeCount} active</p>
                </div>
                <Button variant="outline" size="sm" onClick={() => setCreateOpen(true)}>
                  <Plus />
                  Create
                </Button>
              </div>

              {automations.length === 0 ? (
                <EmptyState
                  icon={Workflow}
                  title="No automations yet"
                  description="Create your first automation to orchestrate agent work through a reusable workflow."
                  actionLabel="Create Automation"
                  onAction={() => setCreateOpen(true)}
                />
              ) : (
                <div className="automations-table" role="list">
                  {automations.map((automation) => (
                    <article key={automation.automation_id} className="automations-row" role="listitem">
                      <Link className="automations-row__main" to={`/dashboard/automations/${automation.automation_id}`}>
                        <span className="automations-row__icon">
                          <Workflow />
                        </span>
                        <span className="automations-row__text">
                          <strong>{automation.title}</strong>
                          <span>{automation.description || "No description provided."}</span>
                        </span>
                      </Link>
                      <div className="automations-row__meta">
                        <StatusBadge status={badgeStatus(automation.status)} label={statusLabel(automation.status)} />
                        <span>v{automation.version}</span>
                        <span>Updated {formatDate(automation.updated_at ?? automation.created_at)}</span>
                      </div>
                      <div className="automations-row__actions">
                        <Button variant="ghost" size="icon" asChild>
                          <Link to={`/dashboard/automations/${automation.automation_id}`} aria-label={`Open ${automation.title}`}>
                            <Settings />
                          </Link>
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="text-[var(--danger)] hover:text-[var(--danger)]"
                          aria-label={`Delete ${automation.title}`}
                          onClick={() => {
                            setSelectedAutomation(automation);
                            setDeleteOpen(true);
                          }}
                        >
                          <Trash2 />
                        </Button>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <aside className="automations-aside">
            <Card>
              <CardContent className="automations-aside-card">
                <div className="automations-section-header">
                  <div>
                    <h2>Workflow Setup</h2>
                    <p>Recommended path for reliable runs.</p>
                  </div>
                </div>
                <ol className="automations-checklist">
                  <li>
                    <span>1</span>
                    <div>
                      <strong>Build the graph</strong>
                      <p>Add steps, branches, and final outputs.</p>
                    </div>
                  </li>
                  <li>
                    <span>2</span>
                    <div>
                      <strong>Test with sample input</strong>
                      <p>Inspect step inputs, outputs, and tool calls.</p>
                    </div>
                  </li>
                  <li>
                    <span>3</span>
                    <div>
                      <strong>Add triggers</strong>
                      <p>Run manually or schedule recurring work.</p>
                    </div>
                  </li>
                </ol>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="automations-aside-card">
                <div className="automations-aside-card__icon">
                  <ShoppingBag />
                </div>
                <h2>Use a template</h2>
                <p>Import a proven workflow and configure only the agents, skills, and secrets you own.</p>
                <Button variant="outline" size="sm" onClick={() => navigate("/dashboard/automations/marketplace")}>
                  Browse marketplace
                </Button>
              </CardContent>
            </Card>
          </aside>
        </div>
      </PageBody>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Automation</DialogTitle>
            <DialogDescription>Name the workflow before opening the builder.</DialogDescription>
          </DialogHeader>
          <Stack gap="md">
            <FieldGroup>
              <Label htmlFor="automation-title">Title</Label>
              <Input
                id="automation-title"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="Customer intake workflow"
              />
            </FieldGroup>
            <FieldGroup>
              <Label htmlFor="automation-description">Description</Label>
              <Textarea
                id="automation-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Describe what this workflow automates"
              />
            </FieldGroup>
          </Stack>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={saving || !title.trim()}>
              {saving ? "Creating..." : "Create"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Automation</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete "{selectedAutomation?.title}"? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteOpen(false)} disabled={deleting}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDelete} disabled={deleting}>
              {deleting ? "Deleting..." : "Delete Automation"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Page>
  );
}

function MetricCard({
  label,
  value,
  detail,
  icon: Icon,
}: {
  label: string;
  value: number;
  detail: string;
  icon: LucideIcon;
}) {
  return (
    <Card className="automations-metric">
      <CardContent className="automations-metric__content">
        <span className="automations-metric__icon">
          <Icon />
        </span>
        <span>
          <span className="automations-metric__label">{label}</span>
          <strong>{value}</strong>
          <span className="automations-metric__detail">{detail}</span>
        </span>
      </CardContent>
    </Card>
  );
}
