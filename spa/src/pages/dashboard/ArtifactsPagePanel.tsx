import { ExternalLink, FileText, RefreshCw, Trash2, X } from "lucide-react";
import { Page, PageBody } from "../../components/layout/Page";
import { Alert, AlertDescription, AlertTitle } from "../../components/ui/alert";
import { Button } from "../../components/ui/button";
import { Checkbox } from "../../components/ui/checkbox";
import { InlineEmptyState } from "../../components/ui/empty-state";
import { LinkButton } from "../../components/ui/link-button";
import { Pill } from "../../components/ui/pill";
import { Spinner } from "../../components/ui/spinner";
import type { ArtifactResponse } from "../../services/artifacts";
import { artifactSelectionState, type ArtifactNotification } from "./artifactDeletion";
import styles from "./ArtifactsPage.module.css";

export interface ArtifactsPagePanelProps {
  artifacts: ArtifactResponse[];
  selected: string[];
  loading: boolean;
  error: string | null;
  locked: boolean;
  notification: ArtifactNotification | null;
  onReload: () => void;
  onDismiss: () => void;
  onSelectionChange: (ids: string[]) => void;
  onDelete: (artifact: ArtifactResponse) => void;
  onBulkDelete: () => void;
}

export function ArtifactsPagePanel({ artifacts, selected, loading, error, locked, notification, onReload, onDismiss, onSelectionChange, onDelete, onBulkDelete }: ArtifactsPagePanelProps) {
  const disabled = loading || locked;
  const ids = artifacts.map((artifact) => artifact.artifact_id);
  const { all, mixed } = artifactSelectionState(selected, ids);
  return (
    <Page>
      <PageBody>
        <section className={styles.content} aria-labelledby="artifacts-heading" aria-busy={loading || locked}>
          <div className={styles.header}>
            <div className={styles.headingGroup}>
              <h2 id="artifacts-heading" className={styles.heading}>Artifacts</h2>
              <Pill size="sm" variant="secondary">{artifacts.length}</Pill>
            </div>
            <Button type="button" variant="outline" size="sm" disabled={disabled} onClick={() => { if (!disabled) onReload(); }}>
              <RefreshCw aria-hidden="true" />Reload
            </Button>
          </div>

          {notification && (
            <Alert variant={notification.variant} role={notification.variant === "success" ? "status" : "alert"}
              aria-live={notification.variant === "success" ? "polite" : "assertive"} aria-atomic="true" className={styles.notification}>
              <AlertDescription>{notification.message}</AlertDescription>
              <Button type="button" variant="ghost" size="icon" aria-label="Dismiss notification" onClick={onDismiss}><X aria-hidden="true" /></Button>
            </Alert>
          )}
          {loading && <p role="status" className={styles.loading}><Spinner size="sm" aria-hidden="true" />Loading artifacts…</p>}
          {error && (
            <Alert variant="error" className={styles.error}>
              <AlertTitle>Artifacts unavailable</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
              <Button type="button" variant="outline" size="sm" disabled={disabled} onClick={() => { if (!disabled) onReload(); }}><RefreshCw aria-hidden="true" />Retry</Button>
            </Alert>
          )}
          {!loading && !error && artifacts.length === 0 && (
            <div className={styles.empty}><InlineEmptyState icon={FileText} title="No artifacts yet" description="Generated reports and files will appear here after an agent or automation creates them." /></div>
          )}
          {artifacts.length > 0 && (
            <div className={styles.panel}>
              <div className={styles.toolbar}>
                <label className={styles.selectAll}>
                  <Checkbox checked={all} aria-checked={mixed ? "mixed" : all} disabled={disabled}
                    ref={(node) => { if (node) node.indeterminate = mixed; }}
                    onChange={(event) => { if (!disabled) onSelectionChange(event.currentTarget.checked ? [...new Set(ids)] : []); }} />
                  Select all loaded artifacts
                </label>
                <div className={styles.actions}>
                  <span className={styles.selectedCount}>{selected.length} selected</span>
                  <Button type="button" variant="outline" size="sm" disabled={disabled || selected.length === 0}
                    onClick={() => { if (!disabled && selected.length > 0) onBulkDelete(); }}><Trash2 aria-hidden="true" />Delete selected</Button>
                </div>
              </div>
              <ul className={styles.list} aria-label="Loaded artifacts">
                {artifacts.map((artifact) => (
                  <li key={artifact.artifact_id} className={styles.row}>
                    <Checkbox aria-label={`Select artifact: ${artifact.title}`} checked={selected.includes(artifact.artifact_id)} disabled={disabled}
                      onChange={(event) => {
                        if (disabled) return;
                        onSelectionChange(event.currentTarget.checked ? [...new Set([...selected, artifact.artifact_id])] : selected.filter((id) => id !== artifact.artifact_id));
                      }} />
                    <div className={styles.details}>
                      <p className={styles.artifactTitle}>{artifact.title}</p>
                      <p className={styles.metadata}>{artifact.artifact_type.replaceAll("_", " ")} · {formatBytes(artifact.size_bytes)} · <time dateTime={artifact.created_at}>{new Date(artifact.created_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}</time></p>
                    </div>
                    <div className={styles.rowActions}>
                      {artifact.view_url && <LinkButton to={`/dashboard/artifacts/${artifact.artifact_id}`} variant="outline" size="sm"><ExternalLink aria-hidden="true" />Open</LinkButton>}
                      <Button type="button" variant="ghost" size="icon" className={styles.deleteAction} aria-label={`Delete artifact: ${artifact.title}`} disabled={disabled}
                        onClick={() => { if (!disabled) onDelete(artifact); }}><Trash2 aria-hidden="true" /></Button>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      </PageBody>
    </Page>
  );
}

function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** index;
  return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
}
