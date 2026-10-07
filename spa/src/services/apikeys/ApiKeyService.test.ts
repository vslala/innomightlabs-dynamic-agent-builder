import { afterEach, describe, expect, it, vi } from "vitest";
import { apiKeyService } from "./ApiKeyService";

afterEach(() => vi.unstubAllGlobals());

function mockHttp() {
  vi.stubGlobal("localStorage", { getItem: () => "dashboard-token" });
  const fetcher = vi.fn().mockImplementation(async (_url: string, init: RequestInit) => new Response(
    JSON.stringify({ key_id: "key", ...JSON.parse(init.body as string) }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  ));
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

describe("widget key guest access", () => {
  it.each([false, true])("sends the create opt-in (%s)", async (allowGuests) => {
    const fetcher = mockHttp();
    const key = await apiKeyService.createApiKey("agent", { name: "Website", allow_guests: allowGuests });
    expect(key.allow_guests).toBe(allowGuests);
    expect(fetcher).toHaveBeenCalledWith(expect.stringContaining("/agents/agent/api-keys"), expect.objectContaining({
      method: "POST", body: JSON.stringify({ name: "Website", allow_guests: allowGuests }),
    }));
  });
  it.each([false, true])("patches only the guest flag (%s)", async (allowGuests) => {
    const fetcher = mockHttp();
    const key = await apiKeyService.updateApiKey("agent", "key", { allow_guests: allowGuests });
    expect(key.allow_guests).toBe(allowGuests);
    expect(fetcher).toHaveBeenCalledWith(expect.stringContaining("/agents/agent/api-keys/key"), expect.objectContaining({
      method: "PATCH", body: JSON.stringify({ allow_guests: allowGuests }),
    }));
  });
});
