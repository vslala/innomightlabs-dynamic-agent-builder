import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import {
  Alert,
  AlertDescription,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  LoadingState,
} from "../../../../components/ui";
import { connectorApiService } from "../../../../services/connectors";
import type { AgentMCPConnection, MCPSharingView } from "../../../../types/connectors";
import { AudiencePicker } from "./AudiencePicker";
import { SharingDisclaimer } from "./SharingDisclaimer";
import { ToolAllowlist } from "./ToolAllowlist";
import {
  canSave,
  initialDraft,
  isShared,
  retiredTools,
  toRequest,
  toggled,
  type SharingDraft,
} from "./sharingDraft";
import styles from "./MCPSharingDialog.module.css";

interface MCPSharingDialogProps {
  connection: AgentMCPConnection;
  onClose: () => void;
  onSaved: () => Promise<void>;
}

/** Lets an owner choose who besides them may use one connector on this agent, and which of its tools. */
export function MCPSharingDialog({ connection, onClose, onSaved }: MCPSharingDialogProps) {
  const { agent_id: agentId, mcp_id: mcpId, name } = connection;
  const [view, setView] = useState<MCPSharingView | null>(null);
  const [draft, setDraft] = useState<SharingDraft | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const show = (loaded: MCPSharingView) => {
    setView(loaded);
    setDraft(initialDraft(loaded));
  };

  useEffect(() => {
    connectorApiService
      .getAgentMCPSharing(agentId, mcpId)
      .then(show)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Failed to load sharing."));
  }, [agentId, mcpId]);

  const update = (changes: Partial<SharingDraft>) => setDraft((current) => current && { ...current, ...changes });

  const refreshTools = async () => {
    if (!view) return;
    setError(null);
    try {
      const catalog = await connectorApiService.refreshMCPToolCatalog(mcpId);
      const refreshed = { ...view, catalog, catalog_error: null };
      const offered = new Set(catalog.tools.map((tool) => tool.name));
      setView(refreshed);
      // A first listing gets the read-only defaults; a re-listing only lets go of tools the server dropped.
      setDraft(
        (current) =>
          current && {
            ...current,
            tools: view.catalog ? current.tools.filter((name) => offered.has(name)) : initialDraft(refreshed).tools,
          }
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : `Couldn't reach ${name} to list its tools.`);
    }
  };

  const save = async (next: SharingDraft) => {
    if (!view) return;
    setSaving(true);
    setError(null);
    try {
      await connectorApiService.updateAgentMCPSharing(agentId, mcpId, toRequest(next, view));
      await onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save sharing.");
    } finally {
      setSaving(false);
    }
  };

  const close = () => {
    if (!saving) onClose();
  };

  const sharingWithSomeone = draft !== null && draft.audiences.length > 0;
  const retired = view ? retiredTools(view) : [];

  return (
    <Dialog open onOpenChange={(open) => !open && close()}>
      <DialogContent className={styles.dialog}>
        <DialogHeader>
          <DialogTitle>Share {name}</DialogTitle>
          <DialogDescription>
            Let people other than you use {name} through this agent. You always keep every tool.
          </DialogDescription>
        </DialogHeader>

        <div className={styles.body}>
          {error && (
            <Alert variant="error">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {!view || !draft ? (
            !error && <LoadingState />
          ) : (
            <>
              <Step number={1} title="Who can use it">
                <AudiencePicker
                  selected={draft.audiences}
                  onToggle={(audience) => update({ audiences: toggled(draft.audiences, audience) })}
                />
              </Step>

              {sharingWithSomeone ? (
                <>
                  <Step number={2} title="Which tools">
                    {view.catalog ? (
                      <ToolAllowlist
                        catalog={view.catalog}
                        selected={draft.tools}
                        onChange={(tools) => update({ tools })}
                        onRefresh={refreshTools}
                      />
                    ) : (
                      <Alert variant="warning">
                        <AlertDescription className={styles.catalogError}>
                          {view.catalog_error}
                          <Button variant="outline" size="sm" onClick={() => void refreshTools()}>
                            Try again
                          </Button>
                        </AlertDescription>
                      </Alert>
                    )}
                    {retired.length > 0 && (
                      <p className={styles.quiet}>
                        No longer offered by {name}, so they will stop being shared: {retired.join(", ")}
                      </p>
                    )}
                  </Step>

                  <Step number={3} title="What this means">
                    <SharingDisclaimer
                      connectionName={name}
                      paragraphs={view.disclaimer.paragraphs}
                      accepted={draft.accepted}
                      onAcceptedChange={(accepted) => update({ accepted })}
                    />
                  </Step>
                </>
              ) : (
                <p className={styles.quiet}>
                  {isShared(view)
                    ? `Saving now stops sharing ${name}. Only you will be able to use it.`
                    : `Only you can use ${name}. Choose who else may, then pick the tools they get.`}
                </p>
              )}
            </>
          )}
        </div>

        <DialogFooter className={styles.footer}>
          {view && isShared(view) && (
            <Button
              variant="ghost"
              className={styles.stopSharing}
              onClick={() => void save({ audiences: [], tools: [], accepted: false })}
              disabled={saving}
            >
              Stop sharing
            </Button>
          )}
          <Button variant="outline" onClick={close} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={() => draft && void save(draft)} disabled={saving || !view || !draft || !canSave(draft, view)}>
            {saving ? "Saving..." : "Save sharing"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Step({ number, title, children }: { number: number; title: string; children: ReactNode }) {
  return (
    <section className={styles.step}>
      <h3 className={styles.stepTitle}>
        <span className={styles.stepNumber}>{number}</span>
        {title}
      </h3>
      {children}
    </section>
  );
}
