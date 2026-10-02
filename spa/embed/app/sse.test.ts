import { describe, expect, it } from "vitest";

import { parseSSE, readSSE } from "./sse";

function streamOf(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
      controller.close();
    },
  });
}

describe("parseSSE", () => {
  it("parses complete blocks and keeps the incomplete tail", () => {
    const { events, rest } = parseSSE<{ n: number }>('data: {"n":1}\n\ndata: {"n":2}\n\ndata: {"n"');

    expect(events).toEqual([{ n: 1 }, { n: 2 }]);
    expect(rest).toBe('data: {"n"');
  });

  it("ignores ids, event names, [DONE] and malformed blocks", () => {
    const { events } = parseSSE('id: 1\nevent: x\ndata: {"n":1}\n\ndata: [DONE]\n\ndata: {oops\n\n');

    expect(events).toEqual([{ n: 1 }]);
  });

  it("handles CRLF line endings", () => {
    expect(parseSSE('data: {"n":1}\r\n\r\n').events).toEqual([{ n: 1 }]);
  });
});

describe("readSSE", () => {
  it("reassembles events split across chunks, including a final block without a blank line", async () => {
    const events = [];
    for await (const event of readSSE(streamOf('data: {"n":', '1}\n\nda', 'ta: {"n":2}'))) {
      events.push(event);
    }

    expect(events).toEqual([{ n: 1 }, { n: 2 }]);
  });
});
