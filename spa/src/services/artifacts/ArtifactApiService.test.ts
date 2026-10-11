import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { artifactApiService } from "./ArtifactApiService";

const values = new Map<string, string>();
beforeEach(() => {
  values.clear();
  values.set("auth_token", "test-token");
  values.set("active_account_id", "account-1");
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  });
  vi.stubGlobal("window", { location: { pathname: "/dashboard/artifacts", href: "/dashboard/artifacts" } });
});
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
function respond(body: unknown, status = 200) {
  const fetcher = vi.fn().mockImplementation(async () => new Response(status === 204 ? null : JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}
const headers = { "Content-Type": "application/json", Authorization: "Bearer test-token", "X-Account-Id": "account-1" };

describe("artifact API", () => {
  it("encodes single DELETE IDs, carries shared headers and resolves 204 without JSON", async () => {
    const fetcher = respond(undefined, 204);
    await expect(artifactApiService.deleteArtifact("a/b ?#")).resolves.toBeUndefined();
    expect(fetcher).toHaveBeenCalledExactlyOnceWith(expect.stringMatching(/\/artifacts\/a%2Fb%20%3F%23$/), { method: "DELETE", headers });
  });

  it("sends bulk DELETE JSON and preserves partial response codes and messages", async () => {
    const result = { deleted_ids: ["a"], failed: [{ artifact_id: "b", code: "DELETE_FAILED", message: "Try again" }] };
    const fetcher = respond(result);
    expect(await artifactApiService.bulkDeleteArtifacts(["a", "b", "a"])).toEqual(result);
    expect(fetcher).toHaveBeenCalledExactlyOnceWith(expect.stringMatching(/\/artifacts\/bulk$/), {
      method: "DELETE", headers, body: JSON.stringify({ artifact_ids: ["a", "b"] }),
    });
  });

  it("bounds deduplicated bulk requests to 100 before issuing HTTP", async () => {
    const fetcher = respond({ deleted_ids: [], failed: [] });
    await expect(artifactApiService.bulkDeleteArtifacts([])).rejects.toThrow("1 and 100");
    await expect(artifactApiService.bulkDeleteArtifacts(Array.from({ length: 101 }, (_, index) => String(index)))).rejects.toThrow("1 and 100");
    expect(fetcher).not.toHaveBeenCalled();
    await artifactApiService.bulkDeleteArtifacts(Array.from({ length: 100 }, (_, index) => String(index)));
    expect(fetcher).toHaveBeenCalledOnce();
  });

  it("resolves an already-deleted artifact as a successful no-op", async () => {
    respond(undefined, 204);
    await expect(artifactApiService.deleteArtifact("missing")).resolves.toBeUndefined();
  });

  it("preserves actual deletion failures", async () => {
    respond({ detail: "Artifact deletion failed" }, 502);
    await expect(artifactApiService.deleteArtifact("a")).rejects.toMatchObject({ status: 502 });
  });

  it.each([403, 500])("preserves bulk HTTP %s errors", async (status) => {
    respond({ detail: { message: "Deletion unavailable" } }, status);
    await expect(artifactApiService.bulkDeleteArtifacts(["a"])).rejects.toMatchObject({ status, message: "Deletion unavailable" });
  });

  it("preserves shared network failure handling", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    await expect(artifactApiService.deleteArtifact("a")).rejects.toMatchObject({ status: 0 });
  });

  it("retains list envelopes and encoded detail, view and download paths", async () => {
    const fetcher = respond({ items: [] });
    expect(await artifactApiService.listArtifacts(100)).toEqual({ items: [] });
    expect(fetcher.mock.calls[0][0]).toMatch(/\/artifacts\?limit=100$/);
    await artifactApiService.getArtifact("a/b");
    await artifactApiService.getViewUrl("a/b");
    await artifactApiService.getDownloadUrl("a/b");
    expect(fetcher.mock.calls.slice(1).map((call) => call[0])).toEqual([
      expect.stringMatching(/\/artifacts\/a%2Fb$/),
      expect.stringMatching(/\/artifacts\/a%2Fb\/view$/),
      expect.stringMatching(/\/artifacts\/a%2Fb\/download$/),
    ]);
  });
});
