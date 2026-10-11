import { useCallback, useEffect, useRef, useState } from "react";
import { artifactApiService, type ArtifactResponse } from "../../services/artifacts";
import { ConfirmationDialog } from "../../components/ui/confirmation-dialog";
import { ArtifactsPagePanel } from "./ArtifactsPagePanel";
import {
  applyArtifactDeletion, artifactDeletionNotification, artifactRequestError,
  confirmArtifactDeletion, intersectArtifactSelection,
  type ArtifactDeletionConfirmation, type ArtifactNotification,
} from "./artifactDeletion";

export function ArtifactsPage() {
  const [listing, setListing] = useState<{ artifacts: ArtifactResponse[]; selected: string[] }>({ artifacts: [], selected: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [confirmation, setConfirmation] = useState<ArtifactDeletionConfirmation | null>(null);
  const [notification, setNotification] = useState<ArtifactNotification | null>(null);
  const pending = useRef<ArtifactDeletionConfirmation | null>(null);
  const inFlight = useRef(false);
  const mounted = useRef(false);
  const loadVersion = useRef(0);

  const loadArtifacts = useCallback(async () => {
    if (inFlight.current || pending.current) return;
    const version = ++loadVersion.current;
    setLoading(true);
    setError(null);
    try {
      const response = await artifactApiService.listArtifacts(100);
      if (!mounted.current || version !== loadVersion.current) return;
      setListing((current) => ({
        artifacts: response.items,
        selected: intersectArtifactSelection(current.selected, response.items.map((artifact) => artifact.artifact_id)),
      }));
    } catch (err) {
      if (mounted.current && version === loadVersion.current) setError(artifactRequestError(err, "load"));
    } finally {
      if (mounted.current && version === loadVersion.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const requests = loadVersion;
    mounted.current = true;
    void loadArtifacts();
    return () => {
      mounted.current = false;
      ++requests.current;
    };
  }, [loadArtifacts]);

  const openConfirmation = (snapshot: ArtifactDeletionConfirmation) => {
    if (loading || inFlight.current || pending.current) return;
    pending.current = { ...snapshot, ids: [...new Set(snapshot.ids)] };
    setConfirmation(pending.current);
  };

  const handleConfirm = () => confirmArtifactDeletion(pending, inFlight, artifactApiService, {
    onStart: () => {
      // Ignore any older fetch even if it completes after deletion.
      ++loadVersion.current;
      setDeleting(true);
      setNotification(null);
    },
    onResult: (result) => {
      if (!mounted.current) return;
      setListing((current) => applyArtifactDeletion(current.artifacts, current.selected, result));
      setNotification(artifactDeletionNotification(result));
    },
    onError: (err) => {
      if (mounted.current) setNotification({ variant: "error", message: artifactRequestError(err, "delete") });
    },
    onFinish: () => {
      if (!mounted.current) return;
      setDeleting(false);
      setConfirmation(null);
    },
  });

  return (
    <>
      <ArtifactsPagePanel
        artifacts={listing.artifacts} selected={listing.selected} loading={loading} error={error}
        locked={deleting || confirmation !== null} notification={notification}
        onReload={() => { void loadArtifacts(); }} onDismiss={() => setNotification(null)}
        onSelectionChange={(ids) => {
          if (loading || inFlight.current || pending.current) return;
          setListing((current) => ({ ...current, selected: intersectArtifactSelection(ids, current.artifacts.map((artifact) => artifact.artifact_id)) }));
        }}
        onDelete={(artifact) => openConfirmation({ kind: "single", ids: [artifact.artifact_id], title: artifact.title })}
        onBulkDelete={() => openConfirmation({ kind: "bulk", ids: [...listing.selected] })}
      />
      <ConfirmationDialog
        open={confirmation !== null}
        onOpenChange={(open) => {
          if (!open && !inFlight.current) {
            pending.current = null;
            setConfirmation(null);
          }
        }}
        title={confirmation?.kind === "single" ? `Delete “${confirmation.title}”?` : `Delete ${confirmation?.ids.length ?? 0} artifacts?`}
        description={confirmation?.kind === "single"
          ? "This will permanently remove this artifact and its file. This action cannot be undone."
          : `This will permanently remove ${confirmation?.ids.length ?? 0} selected artifacts and their files. This action cannot be undone.`}
        confirmText="Delete" variant="destructive" loading={deleting} loadingText="Deleting…" onConfirm={handleConfirm}
      />
    </>
  );
}
