import { describe, expect, it } from "vitest";
import { kindDetails, parseKind } from "./conversationKind";

describe("the conversations tab named in the address", () => {
  it("is chats unless automations were asked for", () => {
    expect(parseKind(null)).toBe("chat");
    expect(parseKind("chat")).toBe("chat");
    expect(parseKind("automation")).toBe("automation");
    expect(parseKind("automations")).toBe("chat");
    expect(parseKind("")).toBe("chat");
  });

  it("says what its list holds", () => {
    expect(kindDetails("automation").noun).toBe("automation runs");
    expect(kindDetails("chat").label).toBe("Chats");
  });
});
