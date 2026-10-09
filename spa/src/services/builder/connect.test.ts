import { describe, expect, it } from "vitest";

import { connectOutcome, connectedMessage, OAUTH_MESSAGE_TYPE } from "./connect";

const ORIGIN = "https://app.innomightlabs.com";

describe("connectOutcome", () => {
  it("believes only our own popup", () => {
    const data = { type: OAUTH_MESSAGE_TYPE, result: { mcp_oauth: "success", mcp_id: "m1" } };
    expect(connectOutcome({ origin: ORIGIN, data }, ORIGIN)).toBe("connected");
    expect(connectOutcome({ origin: "https://evil.example", data }, ORIGIN)).toBeNull();
    expect(connectOutcome({ origin: ORIGIN, data: { type: "other", result: {} } }, ORIGIN)).toBeNull();
  });

  it("reports a sign-in that didn't finish", () => {
    const data = { type: OAUTH_MESSAGE_TYPE, result: { mcp_oauth: "error", reason: "cancelled" } };
    expect(connectOutcome({ origin: ORIGIN, data }, ORIGIN)).toBe("failed");
  });
});

describe("connectedMessage", () => {
  it("names the account", () => {
    expect(connectedMessage("Connect Tavily")).toBe("I've connected Tavily.");
  });
});
