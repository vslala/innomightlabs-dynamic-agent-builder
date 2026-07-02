import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Database, Plus, Trash2, Settings, FileText } from "lucide-react";
import {
  Card,
  CardContent,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  Textarea,
  LoadingState,
  ErrorState,
  EmptyState,
} from "../../components/ui";
import { FieldGroup, Grid, Inline, Page, PageActions, PageBody, PageDescription, PageHeader, Stack } from "../../components/layout";
import { knowledgeApiService } from "../../services/knowledge";
import type { KnowledgeBase } from "../../types/knowledge";

export function KnowledgeBases() {
  const navigate = useNavigate();
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [selectedKB, setSelectedKB] = useState<KnowledgeBase | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const loadKnowledgeBases = async () => {
    try {
      setError(null);
      const data = await knowledgeApiService.listKnowledgeBases();
      setKnowledgeBases(data);
    } catch (err) {
      setError("Failed to load knowledge bases. Please try again.");
      console.error("Error loading knowledge bases:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadKnowledgeBases();
  }, []);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setIsCreating(true);
    try {
      const created = await knowledgeApiService.createKnowledgeBase({
        name: newName.trim(),
        description: newDescription.trim() || undefined,
      });
      setIsCreateDialogOpen(false);
      setNewName("");
      setNewDescription("");
      navigate(`/dashboard/knowledge-bases/${created.kb_id}`);
    } catch (err) {
      console.error("Error creating knowledge base:", err);
    } finally {
      setIsCreating(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedKB) return;
    setIsDeleting(true);
    try {
      await knowledgeApiService.deleteKnowledgeBase(selectedKB.kb_id);
      setIsDeleteDialogOpen(false);
      setSelectedKB(null);
      loadKnowledgeBases();
    } catch (err) {
      console.error("Error deleting knowledge base:", err);
    } finally {
      setIsDeleting(false);
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  if (loading) {
    return <LoadingState />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={loadKnowledgeBases} />;
  }

  return (
    <Page>
      <PageHeader>
        <PageDescription>Create and manage knowledge bases for your AI agents</PageDescription>
        <PageActions>
        <Button onClick={() => setIsCreateDialogOpen(true)} size="lg">
          <Plus className="h-5 w-5" />
          Create Knowledge Base
        </Button>
        </PageActions>
      </PageHeader>

      <PageBody>
        {knowledgeBases.length === 0 ? (
          <EmptyState
            icon={Database}
            title="No knowledge bases yet"
            description="Create a knowledge base to store and search content for your AI agents. You can crawl websites or upload documents."
            actionLabel="Create Your First Knowledge Base"
            onAction={() => setIsCreateDialogOpen(true)}
          />
        ) : (
          <Grid className="grid-cols-1 md:grid-cols-2 lg:grid-cols-3" gap="lg">
            {knowledgeBases.map((kb) => (
              <Card
                key={kb.kb_id}
                className="group hover:border-[var(--gradient-start)]/50 transition-all duration-200"
              >
                <CardContent>
                  <Stack gap="md">
                    <Inline justify="space-between" align="flex-start" wrap={false}>
                      <div className="h-14 w-14 rounded-xl bg-gradient-to-br from-[var(--gradient-start)] to-[var(--gradient-mid)] flex items-center justify-center">
                        <Database className="h-7 w-7 text-white" />
                      </div>
                      <Inline gap="xs" className="opacity-0 transition-opacity group-hover:opacity-100">
                        <Link to={`/dashboard/knowledge-bases/${kb.kb_id}`}>
                          <Button variant="ghost" size="icon">
                            <Settings className="h-4 w-4" />
                          </Button>
                        </Link>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="text-red-400 hover:text-red-300"
                          onClick={() => {
                            setSelectedKB(kb);
                            setIsDeleteDialogOpen(true);
                          }}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </Inline>
                    </Inline>

                    <Stack gap="xs">
                      <Link to={`/dashboard/knowledge-bases/${kb.kb_id}`}>
                        <h3 className="text-lg font-semibold text-[var(--text-primary)] transition-colors hover:text-[var(--gradient-start)]">
                          {kb.name}
                        </h3>
                      </Link>
                      <p className="line-clamp-2 text-sm leading-relaxed text-[var(--text-muted)]">
                        {kb.description || "No description"}
                      </p>
                    </Stack>

                    <Inline className="border-t border-[var(--border-subtle)]" style={{ paddingTop: "var(--space-3)" }}>
                      <Inline gap="xs" className="text-xs text-[var(--text-muted)]">
                        <FileText className="h-3.5 w-3.5" />
                        <span>{kb.total_pages} pages</span>
                      </Inline>
                      <Inline gap="xs" className="text-xs text-[var(--text-muted)]">
                        <Database className="h-3.5 w-3.5" />
                        <span>{kb.total_chunks} chunks</span>
                      </Inline>
                    </Inline>

                    <div className="text-xs text-[var(--text-muted)]">Created {formatDate(kb.created_at)}</div>
                  </Stack>
                </CardContent>
              </Card>
            ))}
          </Grid>
        )}
      </PageBody>

      <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Knowledge Base</DialogTitle>
            <DialogDescription>
              Create a new knowledge base to store content for your AI agents.
            </DialogDescription>
          </DialogHeader>
          <Stack gap="md" style={{ paddingBlock: "var(--space-4)" }}>
            <FieldGroup>
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g., Company Documentation"
              />
            </FieldGroup>
            <FieldGroup>
              <Label htmlFor="description">Description (optional)</Label>
              <Textarea
                id="description"
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
                placeholder="Describe what this knowledge base contains..."
                rows={3}
              />
            </FieldGroup>
          </Stack>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsCreateDialogOpen(false)}
              disabled={isCreating}
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreate}
              disabled={isCreating || !newName.trim()}
            >
              {isCreating ? "Creating..." : "Create Knowledge Base"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Knowledge Base</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete "{selectedKB?.name}"? This will
              remove all crawled content and cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsDeleteDialogOpen(false)}
              disabled={isDeleting}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={isDeleting}
            >
              {isDeleting ? "Deleting..." : "Delete Knowledge Base"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Page>
  );
}
