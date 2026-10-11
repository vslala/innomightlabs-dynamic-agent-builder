import type { ArtifactResponse, BulkArtifactDeletionResponse } from "../../services/artifacts";
import { HttpError } from "../../services/http/client";

export type ArtifactDeletionConfirmation =
  | { kind: "single"; ids: string[]; title: string }
  | { kind: "bulk"; ids: string[] };

export interface ArtifactNotification {
  variant: "success" | "error";
  message: string;
}

export function intersectArtifactSelection(selected: string[], loadedIds: string[]): string[] {
  const loaded = new Set(loadedIds);
  return [...new Set(selected)].filter((id) => loaded.has(id));
}

export function artifactSelectionState(selected: string[], loadedIds: string[]): { all: boolean; mixed: boolean } {
  const count = intersectArtifactSelection(selected, loadedIds).length;
  return { all: loadedIds.length > 0 && count === new Set(loadedIds).size, mixed: count > 0 && count < new Set(loadedIds).size };
}

export function applyArtifactDeletion(artifacts: ArtifactResponse[], selected: string[], result: BulkArtifactDeletionResponse) {
  const deleted = new Set(result.deleted_ids);
  const remaining = artifacts.filter((artifact) => !deleted.has(artifact.artifact_id));
  return {
    artifacts: remaining,
    selected: intersectArtifactSelection(
      [...selected.filter((id) => !deleted.has(id)), ...result.failed.map((failure) => failure.artifact_id)],
      remaining.map((artifact) => artifact.artifact_id),
    ),
  };
}

export function artifactDeletionNotification(result: BulkArtifactDeletionResponse): ArtifactNotification {
  const deleted = new Set(result.deleted_ids).size;
  const failed = result.failed.length;
  const counts = `${deleted} deleted, ${failed} failed.`;
  if (!failed) return { variant: "success", message: counts };

  // Do not expose storage/provider error messages that can contain internal paths or details.
  return { variant: "error", message: `${counts} Failed artifacts remain selected. Retry deletion or reload the list.` };
}

export function artifactRequestError(error: unknown, action: "load" | "delete"): string {
  if (error instanceof HttpError) {

    if (error.status === 401) return "Your session expired. Sign in again.";
    if (error.status === 403) return `You do not have permission to ${action} these artifacts.`;
    if (error.status === 0) return "Connection unavailable. Check your connection and retry.";
  }
  return action === "delete" ? "Unable to delete artifacts. Nothing was removed from this list; retry or reload." : "Unable to load artifacts. Please retry.";
}

/** Reads confirmation at invocation, so cancellation does not retain a stale request. */
export async function confirmArtifactDeletion(
  confirmation: { current: ArtifactDeletionConfirmation | null },
  inFlight: { current: boolean },
  api: {
    deleteArtifact: (id: string) => Promise<void>;
    bulkDeleteArtifacts: (ids: string[]) => Promise<BulkArtifactDeletionResponse>;
  },
  actions: {
    onStart: () => void;
    onResult: (result: BulkArtifactDeletionResponse) => void;
    onError: (error: unknown) => void;
    onFinish: () => void;
  },
): Promise<void> {
  if (!confirmation.current || inFlight.current) return;
  const snapshot = { ...confirmation.current, ids: [...new Set(confirmation.current.ids)] };
  inFlight.current = true;
  actions.onStart();
  try {
    let result: BulkArtifactDeletionResponse;
    if (snapshot.kind === "single") {
      await api.deleteArtifact(snapshot.ids[0]);
      result = { deleted_ids: snapshot.ids, failed: [] };
    } else {
      result = await api.bulkDeleteArtifacts(snapshot.ids);
    }
    actions.onResult(result);
  } catch (error) {
    actions.onError(error);
  } finally {
    confirmation.current = null;
    inFlight.current = false;
    actions.onFinish();
  }
}
