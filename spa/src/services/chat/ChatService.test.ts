import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { chatService } from "./ChatService";

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

    await chatService.sendMessage("agent-1", "conv-1", "what is this?", undefined, ["img-1", "img-2"], false, noHandlers);

    expect(lastRequestBody(fetcher)).toEqual({ content: "what is this?", image_ids: ["img-1", "img-2"] });
  });

  it("leaves image_ids out when there are none, so older servers see the request they know", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(null, { status: 500 }));
    vi.stubGlobal("fetch", fetcher);

    await chatService.sendMessage("agent-1", "conv-1", "hello", undefined, [], false, noHandlers);

    expect(lastRequestBody(fetcher)).toEqual({ content: "hello" });
  });

  it("reports the API's message when it refuses an image, not [object Object]", async () => {
    const detail = { code: "image_not_found", message: "An attached image expired or wasn't found. Please attach it again." };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail }), { status: 422 })));
    const onError = vi.fn();

    await chatService.sendMessage("agent-1", "conv-1", "hi", undefined, ["gone"], false, { ...noHandlers, onError });

    expect(onError).toHaveBeenCalledWith(new Error(detail.message));
  });

  it("still reports a plain string detail", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Agent not found" }), { status: 404 })));
    const onError = vi.fn();

    await chatService.sendMessage("agent-1", "conv-1", "hi", undefined, [], false, { ...noHandlers, onError });

    expect(onError).toHaveBeenCalledWith(new Error("Agent not found"));
  });
});
