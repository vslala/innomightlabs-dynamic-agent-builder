import { afterEach, describe, expect, it, vi } from "vitest";
import { kitApiService } from "./KitApiService";

afterEach(() => vi.unstubAllGlobals());

function mockHttp(body: unknown = { ok: true, plan_id: "p1", steps: [], blockers: [], removals: [] }) {
  vi.stubGlobal("localStorage", { getItem: () => "dashboard-token" });
  const fetcher = vi.fn().mockImplementation(async () => new Response(
    JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } },
  ));
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

describe("rolling back and removing a kit", () => {
  it("plans first, then applies only the plan the person saw", async () => {
    const fetcher = mockHttp();
    const plan = await kitApiService.planRollback("k1", 2);
    expect(plan.plan_id).toBe("p1");
    expect(fetcher).toHaveBeenLastCalledWith(expect.stringContaining("/kits/k1/rollback/plan"), expect.objectContaining({
      method: "POST", body: JSON.stringify({ version: 2 }),
    }));

    await kitApiService.rollback("k1", 2, "p1");
    expect(fetcher).toHaveBeenLastCalledWith(expect.stringContaining("/kits/k1/rollback"), expect.objectContaining({
      method: "POST", body: JSON.stringify({ version: 2, plan_id: "p1" }),
    }));
  });

  it("removes with the removal plan's id", async () => {
    const fetcher = mockHttp();
    await kitApiService.planRemoval("k1");
    expect(fetcher).toHaveBeenLastCalledWith(expect.stringContaining("/kits/k1/removal/plan"), expect.anything());
    await kitApiService.remove("k1", "p1");
    expect(fetcher).toHaveBeenLastCalledWith(expect.stringContaining("/kits/k1/remove"), expect.objectContaining({
      method: "POST", body: JSON.stringify({ plan_id: "p1" }),
    }));
  });
});
