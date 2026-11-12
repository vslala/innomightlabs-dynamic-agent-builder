import { afterEach, describe, expect, it, vi } from "vitest";
import { builderApiService } from "./BuilderApiService";

afterEach(() => vi.unstubAllGlobals());

describe("changing Ila's model mid-conversation", () => {
  it("puts the provider and model to her conversation", async () => {
    vi.stubGlobal("localStorage", { getItem: () => "dashboard-token" });
    const fetcher = vi.fn().mockImplementation(async (_url: string, init: RequestInit) => new Response(
      JSON.stringify({ conversation_id: "c1", ...JSON.parse(init.body as string) }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ));
    vi.stubGlobal("fetch", fetcher);

    await builderApiService.changeModel("c1", "Anthropic", "claude-haiku");

    expect(fetcher).toHaveBeenCalledWith(expect.stringContaining("/builder/c1/model"), expect.objectContaining({
      method: "PUT", body: JSON.stringify({ agent_provider: "Anthropic", agent_model: "claude-haiku" }),
    }));
  });
});
