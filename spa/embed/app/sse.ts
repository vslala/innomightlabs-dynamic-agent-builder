/**
 * Incremental Server-Sent Events parsing for the widget message stream
 * (`data: {json}` blocks separated by blank lines).
 */

export interface ParsedChunk<T> {
  events: T[];
  /** An incomplete trailing block, to prepend to the next chunk. */
  rest: string;
}

export function parseSSE<T>(buffer: string): ParsedChunk<T> {
  const blocks = buffer.replace(/\r\n/g, "\n").split("\n\n");
  const rest = blocks.pop() ?? "";
  const events: T[] = [];

  for (const block of blocks) {
    const data = block
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).replace(/^ /, ""))
      .join("\n");
    if (!data || data === "[DONE]") continue;
    try {
      events.push(JSON.parse(data) as T);
    } catch {
      // A malformed block is skipped rather than ending the whole stream.
    }
  }

  return { events, rest };
}

export async function* readSSE<T>(body: ReadableStream<Uint8Array>): AsyncGenerator<T> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += done ? decoder.decode() + "\n\n" : decoder.decode(value, { stream: true });
      const { events, rest } = parseSSE<T>(buffer);
      buffer = rest;
      yield* events;
      if (done) return;
    }
  } finally {
    reader.releaseLock();
  }
}
