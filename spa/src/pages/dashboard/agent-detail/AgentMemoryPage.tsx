import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight, Database, Lock, Pencil, Plus, Trash2 } from "lucide-react";

import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../../../components/ui/dialog";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";
import { Textarea } from "../../../components/ui/textarea";
import {
  memoryApiService,
  type MemoryBlockContentResponse,
  type MemoryBlockResponse,
} from "../../../services/memory";
import { useAgentDetailContext } from "./types";

export function AgentMemoryPage() {
  const { agent } = useAgentDetailContext();
  const [memoryBlocks, setMemoryBlocks] = useState<MemoryBlockResponse[]>([]);
  const [expandedBlocks, setExpandedBlocks] = useState<Set<string>>(new Set());
  const [blockContents, setBlockContents] = useState<Record<string, MemoryBlockContentResponse>>({});
  const [loadingBlocks, setLoadingBlocks] = useState(false);
  const [isCreateBlockDialogOpen, setIsCreateBlockDialogOpen] = useState(false);
  const [newBlockName, setNewBlockName] = useState("");
  const [newBlockDescription, setNewBlockDescription] = useState("");
  const [newBlockWordLimit, setNewBlockWordLimit] = useState(5000);
  const [isCreatingBlock, setIsCreatingBlock] = useState(false);
  const [createBlockError, setCreateBlockError] = useState<string | null>(null);
  const [editingBlock, setEditingBlock] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");
  const [isSavingContent, setIsSavingContent] = useState(false);
  const [deletingBlock, setDeletingBlock] = useState<string | null>(null);
  const [isDeletingBlock, setIsDeletingBlock] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadMemoryBlocks() {
      setLoadingBlocks(true);
      try {
        const blocks = await memoryApiService.listMemoryBlocks(agent.agent_id);
        blocks.sort((a, b) => {
          if (a.is_default && !b.is_default) return -1;
          if (!a.is_default && b.is_default) return 1;
          return a.block_name.localeCompare(b.block_name);
        });
        if (!cancelled) {
          setMemoryBlocks(blocks);
        }
      } catch (err) {
        console.error("Error loading memory blocks:", err);
      } finally {
        if (!cancelled) {
          setLoadingBlocks(false);
        }
      }
    }

    loadMemoryBlocks();

    return () => {
      cancelled = true;
    };
  }, [agent.agent_id]);

  const toggleBlockExpansion = async (blockName: string) => {
    const nextExpanded = new Set(expandedBlocks);
    if (nextExpanded.has(blockName)) {
      nextExpanded.delete(blockName);
      setExpandedBlocks(nextExpanded);
      return;
    }

    nextExpanded.add(blockName);
    setExpandedBlocks(nextExpanded);

    if (blockContents[blockName]) {
      return;
    }

    try {
      const content = await memoryApiService.getMemoryBlockContent(agent.agent_id, blockName);
      setBlockContents((prev) => ({ ...prev, [blockName]: content }));
    } catch (err) {
      console.error(`Error loading content for ${blockName}:`, err);
    }
  };

  const handleCreateBlock = async () => {
    if (!newBlockName.trim() || !newBlockDescription.trim()) return;
    setIsCreatingBlock(true);
    setCreateBlockError(null);

    try {
      const created = await memoryApiService.createMemoryBlock(agent.agent_id, {
        name: newBlockName.trim().toLowerCase().replace(/\s+/g, "_"),
        description: newBlockDescription.trim(),
        word_limit: newBlockWordLimit,
      });

      setMemoryBlocks((prev) =>
        [...prev, created].sort((a, b) => {
          if (a.is_default && !b.is_default) return -1;
          if (!a.is_default && b.is_default) return 1;
          return a.block_name.localeCompare(b.block_name);
        })
      );
      setIsCreateBlockDialogOpen(false);
      setNewBlockName("");
      setNewBlockDescription("");
      setNewBlockWordLimit(5000);
    } catch (err: unknown) {
      setCreateBlockError(err instanceof Error ? err.message : "Failed to create memory block");
    } finally {
      setIsCreatingBlock(false);
    }
  };

  const handleDeleteBlock = async () => {
    if (!deletingBlock) return;
    setIsDeletingBlock(true);
    try {
      await memoryApiService.deleteMemoryBlock(agent.agent_id, deletingBlock);
      setMemoryBlocks((prev) => prev.filter((block) => block.block_name !== deletingBlock));
      setBlockContents((prev) => {
        const next = { ...prev };
        delete next[deletingBlock];
        return next;
      });
      setExpandedBlocks((prev) => {
        const next = new Set(prev);
        next.delete(deletingBlock);
        return next;
      });
      setDeletingBlock(null);
    } catch (err) {
      console.error("Error deleting memory block:", err);
    } finally {
      setIsDeletingBlock(false);
    }
  };

  const handleStartEditContent = (blockName: string) => {
    const content = blockContents[blockName];
    if (!content) return;
    setEditContent(content.lines.join("\n"));
    setEditingBlock(blockName);
  };

  const handleSaveContent = async () => {
    if (!editingBlock) return;
    setIsSavingContent(true);
    try {
      const lines = editContent.split("\n").filter((line) => line.trim() !== "");
      const updated = await memoryApiService.updateMemoryBlockContent(agent.agent_id, editingBlock, {
        lines,
      });
      setBlockContents((prev) => ({ ...prev, [editingBlock]: updated }));
      setMemoryBlocks((prev) =>
        prev.map((block) =>
          block.block_name === editingBlock
            ? { ...block, word_count: updated.word_count, capacity_percent: updated.capacity_percent }
            : block
        )
      );
      setEditingBlock(null);
      setEditContent("");
    } catch (err) {
      console.error("Error saving memory block content:", err);
    } finally {
      setIsSavingContent(false);
    }
  };

  return (
    <>
      <Card>
        <CardHeader>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <Database style={{ height: "1.25rem", width: "1.25rem", color: "var(--gradient-start)" }} />
              <CardTitle className="text-lg">Memory Blocks</CardTitle>
            </div>
            <Button size="sm" onClick={() => setIsCreateBlockDialogOpen(true)}>
              <Plus style={{ height: "1rem", width: "1rem", marginRight: "0.375rem" }} />
              New Block
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loadingBlocks ? (
            <div style={{ display: "flex", justifyContent: "center", padding: "2rem" }}>
              <div style={{ height: "2rem", width: "2rem", animation: "spin 1s linear infinite", borderRadius: "50%", border: "2px solid var(--gradient-start)", borderTopColor: "transparent" }} />
            </div>
          ) : memoryBlocks.length === 0 ? (
            <div style={{ textAlign: "center", padding: "2rem", color: "var(--text-muted)" }}>
              <Database style={{ height: "3rem", width: "3rem", margin: "0 auto 1rem", opacity: 0.5 }} />
              <p>No memory blocks yet</p>
              <p style={{ fontSize: "0.875rem" }}>Memory blocks will be created when you start chatting with this agent</p>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {memoryBlocks.map((block) => (
                <div key={block.block_name} style={{ border: "1px solid var(--border-subtle)", borderRadius: "0.5rem", overflow: "hidden" }}>
                  <div
                    style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0.75rem 1rem", backgroundColor: "var(--bg-secondary)", cursor: "pointer" }}
                    onClick={() => toggleBlockExpansion(block.block_name)}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                      {expandedBlocks.has(block.block_name) ? (
                        <ChevronDown style={{ height: "1rem", width: "1rem", color: "var(--text-muted)" }} />
                      ) : (
                        <ChevronRight style={{ height: "1rem", width: "1rem", color: "var(--text-muted)" }} />
                      )}
                      <div>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                          <span style={{ fontWeight: 500, color: "var(--text-primary)" }}>{block.block_name}</span>
                          {block.is_default && (
                            <span style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", fontSize: "0.75rem", color: "var(--text-muted)", backgroundColor: "var(--bg-tertiary)", padding: "0.125rem 0.5rem", borderRadius: "0.25rem" }}>
                              <Lock style={{ height: "0.625rem", width: "0.625rem" }} />
                              default
                            </span>
                          )}
                        </div>
                        <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.125rem" }}>{block.description}</p>
                      </div>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                      <div style={{ textAlign: "right" }}>
                        <div style={{ fontSize: "0.75rem", color: block.capacity_percent > 80 ? "#f59e0b" : "var(--text-muted)" }}>
                          {block.word_count} / {block.word_limit} words
                        </div>
                        <div style={{ width: "4rem", height: "0.25rem", backgroundColor: "var(--bg-tertiary)", borderRadius: "0.125rem", overflow: "hidden", marginTop: "0.25rem" }}>
                          <div style={{ width: `${Math.min(block.capacity_percent, 100)}%`, height: "100%", backgroundColor: block.capacity_percent > 80 ? "#f59e0b" : "var(--gradient-start)", transition: "width 0.3s ease" }} />
                        </div>
                      </div>
                      {!block.is_default && (
                        <Button
                          variant="ghost"
                          size="icon"
                          style={{ color: "#f87171", height: "2rem", width: "2rem" }}
                          onClick={(event) => {
                            event.stopPropagation();
                            setDeletingBlock(block.block_name);
                          }}
                        >
                          <Trash2 style={{ height: "0.875rem", width: "0.875rem" }} />
                        </Button>
                      )}
                    </div>
                  </div>

                  {expandedBlocks.has(block.block_name) && (
                    <div style={{ padding: "1rem", borderTop: "1px solid var(--border-subtle)" }}>
                      {blockContents[block.block_name] ? (
                        <>
                          {blockContents[block.block_name].lines.length === 0 ? (
                            <p style={{ color: "var(--text-muted)", fontStyle: "italic", fontSize: "0.875rem" }}>No content yet</p>
                          ) : (
                            <div style={{ fontFamily: "monospace", fontSize: "0.8125rem", backgroundColor: "var(--bg-tertiary)", padding: "0.75rem", borderRadius: "0.375rem", maxHeight: "12rem", overflowY: "auto" }}>
                              {blockContents[block.block_name].lines.map((line, idx) => (
                                <div key={idx} style={{ display: "flex", gap: "0.75rem", lineHeight: "1.5" }}>
                                  <span style={{ color: "var(--text-muted)", minWidth: "1.5rem", textAlign: "right" }}>{idx + 1}:</span>
                                  <span style={{ color: "var(--text-primary)" }}>{line}</span>
                                </div>
                              ))}
                            </div>
                          )}
                          {!block.is_default && (
                            <div style={{ marginTop: "0.75rem", display: "flex", justifyContent: "flex-end" }}>
                              <Button size="sm" variant="outline" onClick={() => handleStartEditContent(block.block_name)}>
                                <Pencil style={{ height: "0.875rem", width: "0.875rem", marginRight: "0.375rem" }} />
                                Edit Content
                              </Button>
                            </div>
                          )}
                        </>
                      ) : (
                        <div style={{ display: "flex", justifyContent: "center", padding: "1rem" }}>
                          <div style={{ height: "1.5rem", width: "1.5rem", animation: "spin 1s linear infinite", borderRadius: "50%", border: "2px solid var(--gradient-start)", borderTopColor: "transparent" }} />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={isCreateBlockDialogOpen} onOpenChange={setIsCreateBlockDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Memory Block</DialogTitle>
            <DialogDescription>
              Create a new custom memory block for this agent. The agent can store and recall information in this block.
            </DialogDescription>
          </DialogHeader>
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            {createBlockError && (
              <div style={{ padding: "0.75rem", borderRadius: "0.5rem", backgroundColor: "rgba(239, 68, 68, 0.1)", border: "1px solid rgba(239, 68, 68, 0.2)", color: "#f87171", fontSize: "0.875rem" }}>
                {createBlockError}
              </div>
            )}
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <Label htmlFor="block-name">Block Name *</Label>
              <Input id="block-name" placeholder="e.g., projects, goals, preferences" value={newBlockName} onChange={(e) => setNewBlockName(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""))} />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <Label htmlFor="block-description">Description *</Label>
              <Input id="block-description" placeholder="What information will be stored in this block?" value={newBlockDescription} onChange={(e) => setNewBlockDescription(e.target.value)} />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <Label htmlFor="block-limit">Word Limit</Label>
              <Input id="block-limit" type="number" min={100} max={50000} value={newBlockWordLimit} onChange={(e) => setNewBlockWordLimit(parseInt(e.target.value, 10) || 5000)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsCreateBlockDialogOpen(false)} disabled={isCreatingBlock}>Cancel</Button>
            <Button onClick={handleCreateBlock} disabled={!newBlockName.trim() || !newBlockDescription.trim() || isCreatingBlock}>
              {isCreatingBlock ? "Creating..." : "Create Block"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!deletingBlock} onOpenChange={() => setDeletingBlock(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Memory Block</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete the "{deletingBlock}" memory block? This will permanently delete all content stored in this block.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeletingBlock(null)} disabled={isDeletingBlock}>Cancel</Button>
            <Button variant="destructive" onClick={handleDeleteBlock} disabled={isDeletingBlock}>
              {isDeletingBlock ? "Deleting..." : "Delete Block"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!editingBlock} onOpenChange={() => setEditingBlock(null)}>
        <DialogContent style={{ maxWidth: "36rem" }}>
          <DialogHeader>
            <DialogTitle>Edit Memory Block Content</DialogTitle>
            <DialogDescription>
              Edit the content of the "{editingBlock}" memory block. Each line represents one piece of information.
            </DialogDescription>
          </DialogHeader>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <Label htmlFor="edit-content">Content (one item per line)</Label>
            <Textarea id="edit-content" rows={10} value={editContent} onChange={(e) => setEditContent(e.target.value)} style={{ fontFamily: "monospace", fontSize: "0.875rem" }} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditingBlock(null)} disabled={isSavingContent}>Cancel</Button>
            <Button onClick={handleSaveContent} disabled={isSavingContent}>
              {isSavingContent ? "Saving..." : "Save Changes"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
