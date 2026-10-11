import { describe, expect, it, vi } from "vitest";
import type { ArtifactResponse } from "../../services/artifacts";
import { HttpError } from "../../services/http/client";
import {
  applyArtifactDeletion, artifactDeletionNotification, artifactRequestError, artifactSelectionState,
  confirmArtifactDeletion, intersectArtifactSelection, type ArtifactDeletionConfirmation,
} from "./artifactDeletion";

const artifacts = ["a", "b", "c"].map((artifact_id) => ({ artifact_id })) as ArtifactResponse[];
function setup(confirmation: ArtifactDeletionConfirmation | null) {
  return {
    pending: { current: confirmation }, inFlight: { current: false },
    api: { deleteArtifact: vi.fn().mockResolvedValue(undefined), bulkDeleteArtifacts: vi.fn().mockResolvedValue({ deleted_ids: ["a"], failed: [] }) },
    actions: { onStart: vi.fn(), onResult: vi.fn(), onError: vi.fn(), onFinish: vi.fn() },
  };
}

describe("artifact selection and deletion", () => {
  it("supports empty, mixed, select-all and deduplicated selections", () => {
    expect(artifactSelectionState([], [])).toEqual({ all: false, mixed: false });
    expect(artifactSelectionState(["a"], ["a", "b"])).toEqual({ all: false, mixed: true });
    expect(artifactSelectionState(["a", "b", "a"], ["a", "b"])).toEqual({ all: true, mixed: false });
    expect(artifactSelectionState(["stale"], ["a"])).toEqual({ all: false, mixed: false });
  });

  it("preserves refresh selection only for IDs still loaded without inventing selections", () => {
    expect(intersectArtifactSelection(["a", "b", "a"], ["b", "c"])).toEqual(["b"]);
    expect(intersectArtifactSelection(["a", "b"], ["b", "a", "c"])).toEqual(["a", "b"]);
  });

  it("removes ONLY reported successes and leaves failures visible and selected", () => {
    const result = { deleted_ids: ["a"], failed: [{ artifact_id: "b", code: "DELETE_FAILED" as const, message: "missing" }] };
    expect(applyArtifactDeletion(artifacts, ["a", "c"], result)).toEqual({ artifacts: artifacts.slice(1), selected: ["c", "b"] });
    expect(applyArtifactDeletion(artifacts, ["a", "b"], { deleted_ids: [], failed: [] })).toEqual({ artifacts, selected: ["a", "b"] });
  });

  it("uses exact partial counts, safe failure wording and reload advice", () => {
    const notice = artifactDeletionNotification({ deleted_ids: ["a"], failed: [
      { artifact_id: "b", code: "DELETE_FAILED", message: "private storage path" },
      { artifact_id: "c", code: "DELETE_FAILED", message: "secret provider response" },
    ] });
    expect(notice.variant).toBe("error");
    expect(notice.message).toContain("1 deleted, 2 failed.");
    expect(notice.message).toContain("Failed artifacts remain selected.");
    expect(notice.message).not.toMatch(/private|secret/);
    expect(artifactDeletionNotification({ deleted_ids: ["a"], failed: [] })).toEqual({ variant: "success", message: "1 deleted, 0 failed." });
  });

  it("issues no request when confirmation was cancelled", async () => {
    const state = setup({ kind: "single", ids: ["a"], title: "A" });
    state.pending.current = null;
    await confirmArtifactDeletion(state.pending, state.inFlight, state.api, state.actions);
    expect(state.api.deleteArtifact).not.toHaveBeenCalled();
    expect(state.api.bulkDeleteArtifacts).not.toHaveBeenCalled();
    expect(state.actions.onStart).not.toHaveBeenCalled();
  });

  it("blocks double confirm synchronously, snapshots IDs and stays pending until completion", async () => {
    const state = setup({ kind: "bulk", ids: ["a", "b", "a"] });
    let finish!: (result: { deleted_ids: string[]; failed: [] }) => void;
    state.api.bulkDeleteArtifacts.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    const request = confirmArtifactDeletion(state.pending, state.inFlight, state.api, state.actions);
    expect(state.inFlight.current).toBe(true);
    expect(state.actions.onStart).toHaveBeenCalledOnce();
    expect(state.actions.onFinish).not.toHaveBeenCalled();
    state.pending.current!.ids.push("c");
    await confirmArtifactDeletion(state.pending, state.inFlight, state.api, state.actions);
    expect(state.api.bulkDeleteArtifacts).toHaveBeenCalledExactlyOnceWith(["a", "b"]);
    finish({ deleted_ids: ["a"], failed: [] });
    await request;
    expect(state.actions.onResult).toHaveBeenCalledExactlyOnceWith({ deleted_ids: ["a"], failed: [] });
    expect(state.actions.onFinish).toHaveBeenCalledOnce();
    expect(state.pending.current).toBeNull();
    expect(state.inFlight.current).toBe(false);
  });

  it("reports single success after 204, including already-deleted artifacts", async () => {
    const state = setup({ kind: "single", ids: ["b"], title: "B" });
    await confirmArtifactDeletion(state.pending, state.inFlight, state.api, state.actions);
    expect(state.api.deleteArtifact).toHaveBeenCalledExactlyOnceWith("b");
    expect(state.api.bulkDeleteArtifacts).not.toHaveBeenCalled();
    expect(state.actions.onResult).toHaveBeenCalledExactlyOnceWith({ deleted_ids: ["b"], failed: [] });
  });

  it("does not pretend failed requests succeeded and releases the guard", async () => {
    const state = setup({ kind: "single", ids: ["a"], title: "A" });
    const error = new HttpError(502, "private detail");
    state.api.deleteArtifact.mockRejectedValue(error);
    await confirmArtifactDeletion(state.pending, state.inFlight, state.api, state.actions);
    expect(state.actions.onError).toHaveBeenCalledExactlyOnceWith(error);
    expect(state.actions.onResult).not.toHaveBeenCalled();
    expect(state.inFlight.current).toBe(false);
    expect(state.actions.onFinish).toHaveBeenCalledOnce();
    expect(artifactRequestError(error, "delete")).toContain("Nothing was removed");
    expect(artifactRequestError(new Error("private detail"), "delete")).not.toContain("private");
  });
});
