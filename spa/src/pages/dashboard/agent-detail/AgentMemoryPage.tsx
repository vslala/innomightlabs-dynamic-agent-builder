import { useEffect, useState } from "react";
import { Database, Lock, Pencil, Plus, Trash2 } from "lucide-react";

import { FieldGroup, Inline, Stack } from "../../../components/layout";
import {
  AlertBanner,
  Button,
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogSection,
  DialogTitle,
  ExpandableCard,
  InlineEmptyState,
  Input,
  Label,
  LoadingState,
  Panel,
  PanelBody,
  PanelHeader,
  PanelTitle,
  Pill,
  ProgressBar,
  Textarea,
} from "../../../components/ui";
import {
  memoryApiService,
  type MemoryBlockContentResponse,
  type MemoryBlockResponse,
} from "../../../services/memory";
import { useAgentDetailContext } from "./types";
import styles from "./AgentMemoryPage.module.css";

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
      <Panel>
        <PanelHeader>
          <Inline justify="space-between" className={styles.panelHeaderRow}>
            <Inline gap="sm">
              <Database className={styles.panelIcon} />
              <PanelTitle className={styles.panelTitle}>Memory Blocks</PanelTitle>
            </Inline>
            <Button size="sm" onClick={() => setIsCreateBlockDialogOpen(true)}>
              <Plus className={styles.newBlockIcon} />
              New Block
            </Button>
          </Inline>
        </PanelHeader>
        <PanelBody>
          {loadingBlocks ? (
            <LoadingState className={styles.blocksLoadingState} size="default" />
          ) : memoryBlocks.length === 0 ? (
            <InlineEmptyState
              icon={Database}
              title="No memory blocks yet"
              description="Memory blocks will be created when you start chatting with this agent"
            />
          ) : (
            <Stack gap="md">
              {memoryBlocks.map((block) => (
                <ExpandableCard
                  key={block.block_name}
                  expanded={expandedBlocks.has(block.block_name)}
                  onToggle={() => toggleBlockExpansion(block.block_name)}
                  header={
                    <Inline justify="space-between" wrap={false}>
                      <Inline gap="sm" wrap={false}>
                        <div className={styles.blockTitleWrap}>
                          <Inline gap="xs">
                            <span className={styles.blockName}>{block.block_name}</span>
                            {block.is_default && (
                              <Pill size="sm">
                                <Lock className={styles.defaultPillIcon} />
                                default
                              </Pill>
                            )}
                          </Inline>
                          <p className={styles.blockDescription}>
                            {block.description}
                          </p>
                        </div>
                      </Inline>
                      <Inline gap="sm" wrap={false}>
                        <div className={styles.blockStatsCol}>
                          <div
                            className={styles.wordCountLabel}
                            style={{ color: block.capacity_percent > 80 ? "var(--warning)" : "var(--text-muted)" }}
                          >
                            {block.word_count} / {block.word_limit} words
                          </div>
                          <div className={styles.progressBarWrap}>
                            <ProgressBar
                              value={block.word_count}
                              max={block.word_limit}
                              showLabel={false}
                              size="sm"
                            />
                          </div>
                        </div>
                        {!block.is_default && (
                          <Button
                            variant="ghost"
                            size="icon"
                            className={styles.deleteBlockButton}
                            onClick={(event) => {
                              event.stopPropagation();
                              setDeletingBlock(block.block_name);
                            }}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        )}
                      </Inline>
                    </Inline>
                  }
                >
                  {blockContents[block.block_name] ? (
                    <Stack gap="sm">
                      {blockContents[block.block_name].lines.length === 0 ? (
                        <p className={styles.emptyContentText}>No content yet</p>
                      ) : (
                        <div className={styles.contentLines}>
                          {blockContents[block.block_name].lines.map((line, idx) => (
                            <div key={idx} className={styles.contentLineRow}>
                              <span className={styles.contentLineNumber}>{idx + 1}:</span>
                              <span className={styles.contentLineText}>{line}</span>
                            </div>
                          ))}
                        </div>
                      )}
                      {!block.is_default && (
                        <Inline justify="flex-end">
                          <Button size="sm" variant="outline" onClick={() => handleStartEditContent(block.block_name)}>
                            <Pencil className="h-3.5 w-3.5" />
                            Edit Content
                          </Button>
                        </Inline>
                      )}
                    </Stack>
                  ) : (
                    <LoadingState className={styles.contentLoadingState} size="sm" />
                  )}
                </ExpandableCard>
              ))}
            </Stack>
          )}
        </PanelBody>
      </Panel>

      <Dialog open={isCreateBlockDialogOpen} onOpenChange={setIsCreateBlockDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Memory Block</DialogTitle>
            <DialogDescription>
              Create a new custom memory block for this agent. The agent can store and recall information in this block.
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            {createBlockError && <AlertBanner message={createBlockError} variant="error" />}
            <FieldGroup>
              <Label htmlFor="block-name">Block Name *</Label>
              <Input id="block-name" placeholder="e.g., projects, goals, preferences" value={newBlockName} onChange={(e) => setNewBlockName(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""))} />
            </FieldGroup>
            <FieldGroup>
              <Label htmlFor="block-description">Description *</Label>
              <Input id="block-description" placeholder="What information will be stored in this block?" value={newBlockDescription} onChange={(e) => setNewBlockDescription(e.target.value)} />
            </FieldGroup>
            <FieldGroup>
              <Label htmlFor="block-limit">Word Limit</Label>
              <Input id="block-limit" type="number" min={100} max={50000} value={newBlockWordLimit} onChange={(e) => setNewBlockWordLimit(parseInt(e.target.value, 10) || 5000)} />
            </FieldGroup>
          </DialogBody>
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
          <DialogSection>
          <FieldGroup>
            <Label htmlFor="edit-content">Content (one item per line)</Label>
            <Textarea id="edit-content" rows={10} value={editContent} onChange={(e) => setEditContent(e.target.value)} className={styles.editContentTextarea} />
          </FieldGroup>
          </DialogSection>
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
