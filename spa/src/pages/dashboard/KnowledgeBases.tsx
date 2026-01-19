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
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[var(--text-secondary)] text-base">
            Create and manage knowledge bases for your AI agents
          </p>
        </div>
        <Button onClick={() => setIsCreateDialogOpen(true)} size="lg">
          <Plus className="h-5 w-5 mr-2" />
          Create Knowledge Base
        </Button>
      </div>

      {knowledgeBases.length === 0 ? (
        <EmptyState
          icon={Database}
          title="No knowledge bases yet"
          description="Create a knowledge base to store and search content for your AI agents. You can crawl websites or upload documents."
          actionLabel="Create Your First Knowledge Base"
          onAction={() => setIsCreateDialogOpen(true)}
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {knowledgeBases.map((kb) => (
            <Card
              key={kb.kb_id}
              className="group hover:border-[var(--gradient-start)]/50 transition-all duration-200"
            >
              <CardContent className="p-6">
                <div className="flex items-start justify-between mb-5">
                  <div className="h-14 w-14 rounded-xl bg-gradient-to-br from-[var(--gradient-start)] to-[var(--gradient-mid)] flex items-center justify-center">
                    <Database className="h-7 w-7 text-white" />
                  </div>
                  <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Link to={`/dashboard/knowledge-bases/${kb.kb_id}`}>
                      <Button variant="ghost" size="icon" className="h-9 w-9">
                        <Settings className="h-4 w-4" />
                      </Button>
                    </Link>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-9 w-9 text-red-400 hover:text-red-300"
                      onClick={() => {
                        setSelectedKB(kb);
                        setIsDeleteDialogOpen(true);
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>

                <Link to={`/dashboard/knowledge-bases/${kb.kb_id}`}>
                  <h3 className="font-semibold text-lg text-[var(--text-primary)] mb-2 hover:text-[var(--gradient-start)] transition-colors">
                    {kb.name}
                  </h3>
                </Link>
                <p className="text-sm text-[var(--text-muted)] line-clamp-2 mb-4 leading-relaxed">
                  {kb.description || "No description"}
                </p>

                <div className="flex items-center gap-4 pt-2 border-t border-[var(--border-subtle)]">
                  <div className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
                    <FileText className="h-3.5 w-3.5" />
                    <span>{kb.total_pages} pages</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
                    <Database className="h-3.5 w-3.5" />
                    <span>{kb.total_chunks} chunks</span>
                  </div>
                </div>

                <div className="mt-3 text-xs text-[var(--text-muted)]">
                  Created {formatDate(kb.created_at)}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Knowledge Base</DialogTitle>
            <DialogDescription>
              Create a new knowledge base to store content for your AI agents.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g., Company Documentation"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">Description (optional)</Label>
              <Textarea
                id="description"
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
                placeholder="Describe what this knowledge base contains..."
                rows={3}
              />
            </div>
          </div>
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
    </div>
  );
}
