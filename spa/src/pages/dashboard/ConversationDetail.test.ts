import { describe, expect, it } from "vitest";
import source from "./ConversationDetail.tsx?raw";

// Guard the page-level wiring: the chat form already owns its local submitting state.
describe("conversation form submission UI", () => {
  it("does not keep a second, persistent processing notice after form submission", () => {
    expect(source).not.toContain("pendingFormLabel");
    expect(source).not.toContain("setPendingFormLabel");
    expect(source).not.toContain('Captured "');
  });

  it("disables the active form only while a turn is sending", () => {
    const form = source.match(/<ChatFormRenderer\b[\s\S]*?\/>/)?.[0];
    expect(form).toBeDefined();
    expect(form).toContain("disabled={isSending}");
    expect(form).toContain("onSubmit={handleFormSubmit}");
  });

  it("keeps submission history and Ila's live working indicator", () => {
    expect(source).toContain("`Submitted: ${label}`");
    expect(source).toContain("<IlaWorking label={ilaWorkingStatus} />");
  });
});
