import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Plus, Settings, Trash2, Workflow } from "lucide-react";

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
import { automationApiService } from "../../../services/automations";
import type { AutomationResponse } from "../../../types/automation";

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

function badgeStatus(status: AutomationResponse["status"]) {
  return status === "active" ? "active" : "inactive";
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

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-[var(--text-secondary)] text-base">
            Build and test workflow automations for your agents
          </p>
        </div>
        <Button size="lg" onClick={() => setCreateOpen(true)}>
          <Plus className="h-5 w-5" />
          Create Automation
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
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {automations.map((automation) => (
            <Card
              key={automation.automation_id}
              className="group hover:border-[var(--gradient-start)]/50 transition-all duration-200"
            >
              <CardContent className="p-6">
                <div className="flex items-start justify-between mb-5">
                  <div className="h-14 w-14 rounded-xl bg-gradient-to-br from-[var(--gradient-start)] to-[var(--gradient-mid)] flex items-center justify-center">
                    <Workflow className="h-7 w-7 text-white" />
                  </div>
                  <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Link to={`/dashboard/automations/${automation.automation_id}`}>
                      <Button variant="ghost" size="icon">
                        <Settings className="h-4 w-4" />
                      </Button>
                    </Link>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="text-red-400 hover:text-red-300"
                      onClick={() => {
                        setSelectedAutomation(automation);
                        setDeleteOpen(true);
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>

                <Link to={`/dashboard/automations/${automation.automation_id}`}>
                  <h3 className="font-semibold text-lg text-[var(--text-primary)] mb-2 hover:text-[var(--gradient-start)] transition-colors">
                    {automation.title}
                  </h3>
                </Link>
                <p className="text-sm text-[var(--text-muted)] line-clamp-2 mb-4 leading-relaxed">
                  {automation.description || "No description provided."}
                </p>

                <div className="flex items-center justify-between gap-3 pt-2">
                  <StatusBadge status={badgeStatus(automation.status)} label={automation.status} />
                  <span className="text-xs text-[var(--text-muted)]">
                    Updated {formatDate(automation.updated_at ?? automation.created_at)}
                  </span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Automation</DialogTitle>
            <DialogDescription>Name the workflow before opening the builder.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="automation-title">Title</Label>
              <Input
                id="automation-title"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="Customer intake workflow"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="automation-description">Description</Label>
              <Textarea
                id="automation-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Describe what this workflow automates"
              />
            </div>
          </div>
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
    </div>
  );
}
