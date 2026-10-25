import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { chatService, sendMessageBody } from "./ChatService";

const noHandlers = { onEvent: vi.fn() };

beforeEach(() => {
  vi.stubGlobal("localStorage", { getItem: () => null, setItem: vi.fn(), removeItem: vi.fn() });
});
afterEach(() => vi.unstubAllGlobals());

function lastRequestBody(fetcher: ReturnType<typeof vi.fn>): Record<string, unknown> {
  return JSON.parse((fetcher.mock.calls[0][1] as RequestInit).body as string);
}

describe("sending a message with images", () => {
  it("sends the uploaded image ids beside the text", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(null, { status: 500 }));
    vi.stubGlobal("fetch", fetcher);

    await chatService.sendMessage("agent-1", "conv-1", { content: "what is this?", imageIds: ["img-1", "img-2"] }, noHandlers);

    expect(lastRequestBody(fetcher)).toEqual({ content: "what is this?", image_ids: ["img-1", "img-2"] });
  });

  it("leaves image_ids out when there are none, so older servers see the request they know", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(null, { status: 500 }));
    vi.stubGlobal("fetch", fetcher);

    await chatService.sendMessage("agent-1", "conv-1", { content: "hello", imageIds: [] }, noHandlers);

    expect(lastRequestBody(fetcher)).toEqual({ content: "hello" });
  });

  it("reports the API's message when it refuses an image, not [object Object]", async () => {
    const detail = { code: "image_not_found", message: "An attached image expired or wasn't found. Please attach it again." };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail }), { status: 422 })));
    const onError = vi.fn();

    await chatService.sendMessage("agent-1", "conv-1", { content: "hi", imageIds: ["gone"] }, { ...noHandlers, onError });

    expect(onError).toHaveBeenCalledWith(new Error(detail.message));
  });

  it("still reports a plain string detail", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Agent not found" }), { status: 404 })));
    const onError = vi.fn();

    await chatService.sendMessage("agent-1", "conv-1", { content: "hi" }, { ...noHandlers, onError });

    expect(onError).toHaveBeenCalledWith(new Error("Agent not found"));
  });
});

describe("sending a message with documents", () => {
  it("sends each document as a reference by kind and id, without the label", () => {
    const body = sendMessageBody({
      content: "what is my net pay?",
      references: [{ kind: "document", id: "doc-1", label: "payslip.pdf" }],
    });

    expect(body).toEqual({ content: "what is my net pay?", references: [{ kind: "document", id: "doc-1" }] });
  });

  it("leaves references out when there are none", () => {
    expect(sendMessageBody({ content: "hi", references: [] })).toEqual({ content: "hi" });
  });
});
