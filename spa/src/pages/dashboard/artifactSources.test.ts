import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ArtifactResponse, ArtifactSource } from "../../services/artifacts";
import { httpClient } from "../../services/http/client";
import { EMPTY_ARTIFACT_SOURCE_NAMES, resolveArtifactSourceNames } from "./artifactSources";

vi.mock("../../services/http/client", () => ({ httpClient: { get: vi.fn() } }));
const get = vi.mocked(httpClient.get);
const artifact = (source: Partial<ArtifactSource>): ArtifactResponse => ({
  artifact_id: "artifact", artifact_type: "file", title: "Report", filename: "report.txt",
  mime_type: "text/plain", size_bytes: 10, created_at: "2026-10-20T00:00:00Z",
  source: { metadata: {}, ...source },
});
const page = (items: { conversation_id: string; title: string }[], next_cursor: string | null = null) => ({
  items, next_cursor, has_more: next_cursor !== null,
});

beforeEach(() => { get.mockReset(); });

describe("artifact source names", () => {
  it("does not request absent source kinds, including empty and legacy sources", async () => {
    expect(await resolveArtifactSourceNames([])).toEqual(EMPTY_ARTIFACT_SOURCE_NAMES);
    expect(await resolveArtifactSourceNames([artifact({}), artifact({ agent_id: null, skill_id: "" })]))
      .toEqual(EMPTY_ARTIFACT_SOURCE_NAMES);
    expect(get).not.toHaveBeenCalled();
  });

  it("batches duplicate sources through real service list routes and retains only referenced IDs", async () => {
    get.mockImplementation(async (url) => {
      switch (url) {
        case "/agents": return [
          { agent_id: "agent", agent_name: "Researcher" },
          { agent_id: "unrelated", agent_name: "Other agent" },
        ];
        case "/automations": return [
          { automation_id: "automation", title: "Daily report" },
          { automation_id: "unrelated", title: "Other automation" },
        ];
        case "/skills": return [
          { skill_id: "skill", name: "HTML reports" },
          { skill_id: "unrelated", name: "Other skill" },
        ];
        case "/conversations/?limit=100": return page([
          { conversation_id: "conversation", title: "Quarterly research" },
          { conversation_id: "unrelated", title: "Other conversation" },
        ], "unused");
        default: throw new Error(`Unexpected route: ${url}`);
      }
    });
    const source = { agent_id: "agent", automation_id: "automation", skill_id: "skill", conversation_id: "conversation" };
    const result = await resolveArtifactSourceNames(Array.from({ length: 100 }, () => artifact(source)));
    expect(result).toEqual({
      agents: { agent: "Researcher" }, automations: { automation: "Daily report" },
      conversations: { conversation: "Quarterly research" }, skills: { skill: "HTML reports" },
    });
    expect(get).toHaveBeenCalledTimes(4);
  });

  it("leaves deleted, unknown and blank names unresolved rather than inventing names", async () => {
    get.mockResolvedValueOnce([{ agent_id: "blank", agent_name: "  " }])
      .mockResolvedValueOnce([{ skill_id: "blank", name: "" }])
      .mockResolvedValueOnce(page([{ conversation_id: "blank", title: " " }]));
    expect(await resolveArtifactSourceNames([
      artifact({ agent_id: "deleted", skill_id: "unknown", conversation_id: "deleted" }),
      artifact({ agent_id: "blank", skill_id: "blank", conversation_id: "blank" }),
    ])).toEqual(EMPTY_ARTIFACT_SOURCE_NAMES);
  });

  it("isolates a failed source list while preserving successful names", async () => {
    get.mockImplementation(async (url) => {
      if (url === "/skills") return [{ skill_id: "skill", name: "Reports" }];
      throw new Error("Forbidden or unavailable");
    });
    expect(await resolveArtifactSourceNames([artifact({
      agent_id: "agent", automation_id: "automation", conversation_id: "conversation", skill_id: "skill",
    })])).toEqual({ ...EMPTY_ARTIFACT_SOURCE_NAMES, skills: { skill: "Reports" } });
  });

  it("follows conversation cursors and stops once all referenced conversations are found", async () => {
    get.mockResolvedValueOnce(page([{ conversation_id: "first", title: "First" }], "next page"))
      .mockResolvedValueOnce(page([{ conversation_id: "second", title: "Second" }], "unneeded"));
    const result = await resolveArtifactSourceNames([
      artifact({ conversation_id: "first" }), artifact({ conversation_id: "second" }),
    ]);
    expect(result.conversations).toEqual({ first: "First", second: "Second" });
    expect(get.mock.calls.map(([url]) => url)).toEqual([
      "/conversations/?limit=100", "/conversations/?limit=100&cursor=next+page",
    ]);
  });

  it("preserves names from earlier conversation pages if a later page fails", async () => {
    get.mockResolvedValueOnce(page([{ conversation_id: "found", title: "Found" }], "next"))
      .mockRejectedValueOnce(new Error("Unavailable"));
    const result = await resolveArtifactSourceNames([
      artifact({ conversation_id: "found" }), artifact({ conversation_id: "missing" }),
    ]);
    expect(result.conversations).toEqual({ found: "Found" });
  });

  it("bounds conversation scans to five pages even if the source is never found", async () => {
    let cursor = 0;
    get.mockImplementation(async () => page([], `page-${++cursor}`));
    expect(await resolveArtifactSourceNames([artifact({ conversation_id: "old" })]))
      .toEqual(EMPTY_ARTIFACT_SOURCE_NAMES);
    expect(get).toHaveBeenCalledTimes(5);
  });

  it("stops on repeated or missing cursors instead of looping", async () => {
    get.mockResolvedValue(page([], "repeated"));
    await resolveArtifactSourceNames([artifact({ conversation_id: "missing" })]);
    expect(get).toHaveBeenCalledTimes(2);
    get.mockReset().mockResolvedValue({ items: [], has_more: true, next_cursor: null });
    await resolveArtifactSourceNames([artifact({ conversation_id: "missing" })]);
    expect(get).toHaveBeenCalledOnce();
  });

  it("does not start lookups after cleanup and stops pagination when an in-flight lookup is abandoned", async () => {
    const controller = new AbortController();
    controller.abort();
    expect(await resolveArtifactSourceNames([artifact({ agent_id: "agent" })], controller.signal))
      .toEqual(EMPTY_ARTIFACT_SOURCE_NAMES);
    expect(get).not.toHaveBeenCalled();

    const active = new AbortController();
    let finish!: (value: ReturnType<typeof page>) => void;
    get.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    const request = resolveArtifactSourceNames([artifact({ conversation_id: "missing" })], active.signal);
    active.abort();
    finish(page([], "next"));
    await request;
    expect(get).toHaveBeenCalledOnce();
  });

  it("keeps overlapping lookup results independent", async () => {
    let finish!: (value: unknown) => void;
    get.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }))
      .mockResolvedValueOnce([{ agent_id: "new", agent_name: "New agent" }]);
    const oldRequest = resolveArtifactSourceNames([artifact({ agent_id: "old" })]);
    const newResult = await resolveArtifactSourceNames([artifact({ agent_id: "new" })]);
    finish([{ agent_id: "old", agent_name: "Old agent" }]);
    expect((await oldRequest).agents).toEqual({ old: "Old agent" });
    expect(newResult.agents).toEqual({ new: "New agent" });
    expect(EMPTY_ARTIFACT_SOURCE_NAMES.agents).toEqual({});
  });
});
