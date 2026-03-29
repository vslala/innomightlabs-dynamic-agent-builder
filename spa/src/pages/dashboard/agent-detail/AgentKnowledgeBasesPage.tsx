import { useEffect, useState } from "react";
import { BookOpen, Link2, Unlink } from "lucide-react";

import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../../../components/ui/dialog";
import { Label } from "../../../components/ui/label";
import { knowledgeApiService } from "../../../services/knowledge/KnowledgeApiService";
import type { KnowledgeBase } from "../../../types/knowledge";
import { useAgentDetailContext } from "./types";

export function AgentKnowledgeBasesPage() {
  const { agent } = useAgentDetailContext();
  const [linkedKBs, setLinkedKBs] = useState<KnowledgeBase[]>([]);
  const [availableKBs, setAvailableKBs] = useState<KnowledgeBase[]>([]);
  const [loadingKBs, setLoadingKBs] = useState(false);
  const [isLinkKBDialogOpen, setIsLinkKBDialogOpen] = useState(false);
  const [selectedKBToLink, setSelectedKBToLink] = useState("");
  const [isLinkingKB, setIsLinkingKB] = useState(false);
  const [linkKBError, setLinkKBError] = useState<string | null>(null);
  const [unlinkingKB, setUnlinkingKB] = useState<KnowledgeBase | null>(null);
  const [isUnlinkingKB, setIsUnlinkingKB] = useState(false);

  const loadLinkedKBs = async () => {
    setLoadingKBs(true);
    try {
      const kbs = await knowledgeApiService.listAgentKnowledgeBases(agent.agent_id);
      setLinkedKBs(kbs);
    } catch (err) {
      console.error("Error loading linked knowledge bases:", err);
    } finally {
      setLoadingKBs(false);
    }
  };

  useEffect(() => {
    loadLinkedKBs();
  }, [agent.agent_id]);

  const handleOpenLinkDialog = async () => {
    setLinkKBError(null);
    setSelectedKBToLink("");
    try {
      const allKBs = await knowledgeApiService.listKnowledgeBases();
      const linkedIds = new Set(linkedKBs.map((kb) => kb.kb_id));
      setAvailableKBs(allKBs.filter((kb) => !linkedIds.has(kb.kb_id)));
      setIsLinkKBDialogOpen(true);
    } catch (err) {
      console.error("Error loading available knowledge bases:", err);
    }
  };

  const handleLinkKB = async () => {
    if (!selectedKBToLink) return;
    setIsLinkingKB(true);
    setLinkKBError(null);
    try {
      await knowledgeApiService.linkKnowledgeBaseToAgent(agent.agent_id, selectedKBToLink);
      setIsLinkKBDialogOpen(false);
      await loadLinkedKBs();
    } catch (err: unknown) {
      setLinkKBError(err instanceof Error ? err.message : "Failed to link knowledge base");
    } finally {
      setIsLinkingKB(false);
    }
  };

  const handleUnlinkKB = async () => {
    if (!unlinkingKB) return;
    setIsUnlinkingKB(true);
    try {
      await knowledgeApiService.unlinkKnowledgeBaseFromAgent(agent.agent_id, unlinkingKB.kb_id);
      setLinkedKBs((prev) => prev.filter((kb) => kb.kb_id !== unlinkingKB.kb_id));
      setUnlinkingKB(null);
    } catch (err) {
      console.error("Error unlinking knowledge base:", err);
    } finally {
      setIsUnlinkingKB(false);
    }
  };

  return (
    <>
      <Card>
        <CardHeader>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <BookOpen style={{ height: "1.25rem", width: "1.25rem", color: "var(--gradient-start)" }} />
              <CardTitle className="text-lg">Knowledge Bases</CardTitle>
            </div>
            <Button size="sm" onClick={handleOpenLinkDialog}>
              <Link2 style={{ height: "1rem", width: "1rem", marginRight: "0.375rem" }} />
              Link KB
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <p style={{ fontSize: "0.875rem", color: "var(--text-muted)", marginBottom: "1rem" }}>
            Link knowledge bases to give this agent access to your crawled content for RAG-powered responses.
          </p>
          {loadingKBs ? (
            <div style={{ display: "flex", justifyContent: "center", padding: "2rem" }}>
              <div style={{ height: "2rem", width: "2rem", animation: "spin 1s linear infinite", borderRadius: "50%", border: "2px solid var(--gradient-start)", borderTopColor: "transparent" }} />
            </div>
          ) : linkedKBs.length === 0 ? (
            <div style={{ textAlign: "center", padding: "2rem", color: "var(--text-muted)" }}>
              <BookOpen style={{ height: "3rem", width: "3rem", margin: "0 auto 1rem", opacity: 0.5 }} />
              <p>No knowledge bases linked</p>
              <p style={{ fontSize: "0.875rem" }}>Link a knowledge base to enable RAG-powered responses</p>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {linkedKBs.map((kb) => (
                <div key={kb.kb_id} style={{ border: "1px solid var(--border-subtle)", borderRadius: "0.5rem", padding: "1rem" }}>
                  <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "1rem" }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
                        <span style={{ fontWeight: 500, color: "var(--text-primary)" }}>{kb.name}</span>
                        <span style={{ fontSize: "0.75rem", color: kb.status === "active" ? "#10b981" : "var(--text-muted)", backgroundColor: kb.status === "active" ? "rgba(16, 185, 129, 0.1)" : "var(--bg-tertiary)", padding: "0.125rem 0.5rem", borderRadius: "0.25rem" }}>
                          {kb.status}
                        </span>
                      </div>
                      {kb.description && (
                        <p style={{ fontSize: "0.875rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>{kb.description}</p>
                      )}
                      <div style={{ display: "flex", gap: "1rem", fontSize: "0.75rem", color: "var(--text-muted)" }}>
                        <span>{kb.total_pages} pages</span>
                        <span>{kb.total_chunks} chunks</span>
                        <span>{kb.total_vectors} vectors</span>
                      </div>
                    </div>
                    <Button variant="ghost" size="icon" style={{ color: "#f87171", height: "2rem", width: "2rem" }} onClick={() => setUnlinkingKB(kb)} title="Unlink knowledge base">
                      <Unlink style={{ height: "0.875rem", width: "0.875rem" }} />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={isLinkKBDialogOpen} onOpenChange={setIsLinkKBDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Link Knowledge Base</DialogTitle>
            <DialogDescription>
              Select a knowledge base to link to this agent.
            </DialogDescription>
          </DialogHeader>
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            {linkKBError && (
              <div style={{ padding: "0.75rem", borderRadius: "0.5rem", backgroundColor: "rgba(239, 68, 68, 0.1)", border: "1px solid rgba(239, 68, 68, 0.2)", color: "#f87171", fontSize: "0.875rem" }}>
                {linkKBError}
              </div>
            )}
            {availableKBs.length === 0 ? (
              <div style={{ textAlign: "center", padding: "1rem", color: "var(--text-muted)" }}>
                <BookOpen style={{ height: "2rem", width: "2rem", margin: "0 auto 0.5rem", opacity: 0.5 }} />
                <p style={{ fontSize: "0.875rem" }}>No knowledge bases available to link</p>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                <Label>Select Knowledge Base</Label>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", maxHeight: "15rem", overflowY: "auto" }}>
                  {availableKBs.map((kb) => (
                    <div
                      key={kb.kb_id}
                      onClick={() => setSelectedKBToLink(kb.kb_id)}
                      style={{
                        border: selectedKBToLink === kb.kb_id ? "2px solid var(--gradient-start)" : "1px solid var(--border-subtle)",
                        borderRadius: "0.5rem",
                        padding: "0.75rem",
                        cursor: "pointer",
                        backgroundColor: selectedKBToLink === kb.kb_id ? "rgba(255, 255, 255, 0.03)" : "transparent",
                      }}
                    >
                      <div style={{ fontWeight: 500, color: "var(--text-primary)", marginBottom: "0.25rem" }}>{kb.name}</div>
                      {kb.description && <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{kb.description}</p>}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsLinkKBDialogOpen(false)} disabled={isLinkingKB}>Cancel</Button>
            <Button onClick={handleLinkKB} disabled={!selectedKBToLink || isLinkingKB}>
              {isLinkingKB ? "Linking..." : "Link KB"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!unlinkingKB} onOpenChange={() => setUnlinkingKB(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Unlink Knowledge Base</DialogTitle>
            <DialogDescription>
              Are you sure you want to unlink "{unlinkingKB?.name}" from this agent?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setUnlinkingKB(null)} disabled={isUnlinkingKB}>Cancel</Button>
            <Button variant="destructive" onClick={handleUnlinkKB} disabled={isUnlinkingKB}>
              {isUnlinkingKB ? "Unlinking..." : "Unlink"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
