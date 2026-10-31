import { describe, expect, it } from "vitest";
import { parseFormSubmission } from "../../../../components/chat/submittedFormParser";
import { parseConsentDecision } from "../../../../components/chat/consent/consentDecisionParser";
import type { ConsentRequest } from "../../../../types/consent";
import type { Message, SSEEvent } from "../../../../types/message";
import { SSEEventType } from "../../../../types/message";
import {
  appendOnce,
  consentDecisionContent,
  formSubmissionContent,
  generatedImageMessage,
  liveTokenUsageFrom,
  partialImageDataUrl,
} from "./turnMessages";

const event = (fields: Partial<SSEEvent>): SSEEvent =>
  ({ event_type: SSEEventType.TOKEN_USAGE_UPDATE, content: "", ...fields }) as SSEEvent;

describe("liveTokenUsageFrom", () => {
  it("fills missing counts with zero", () => {
    expect(liveTokenUsageFrom(event({ llm_model: "m", total_tokens: 12 }))).toEqual({
      llm_model: "m",
      prompt_tokens: 0,
      completion_tokens: 0,
      total_tokens: 12,
      call_count: 0,
    });
  });

  it("ignores an update without a model", () => {
    expect(liveTokenUsageFrom(event({ total_tokens: 12 }))).toBeNull();
  });
});

describe("partialImageDataUrl", () => {
  it("defaults to PNG", () => {
    expect(partialImageDataUrl(event({ image_b64: "AAA" }))).toBe("data:image/png;base64,AAA");
  });

  it("is null without image data", () => {
    expect(partialImageDataUrl(event({}))).toBeNull();
  });
});

describe("generatedImageMessage", () => {
  it("labels the message by its prompt and keeps the preview", () => {
    const message = generatedImageMessage({
      messageId: "m1",
      conversationId: "c1",
      prompt: "",
      previewDataUrl: "data:x",
      images: [{ image_id: "i1", s3_key: "k", filename: "a.png", mime_type: "image/png", size_bytes: 3, prompt: "p" }],
    });
    expect(message.content).toBe("Generated image: Generated image");
    expect(message.images?.[0]).toMatchObject({ image_id: "i1", preview_data_url: "data:x", prompt: "p" });
  });
});

describe("appendOnce", () => {
  const message = { message_id: "m1" } as Message;

  it("does not add a message twice", () => {
    const messages = [message];
    expect(appendOnce(messages, { ...message })).toBe(messages);
  });

  it("adds a new message at the end", () => {
    expect(appendOnce([message], { message_id: "m2" } as Message).map((m) => m.message_id)).toEqual(["m1", "m2"]);
  });
});

describe("formSubmissionContent", () => {
  it("reads back as the submitted form", () => {
    const content = formSubmissionContent("Contact", [
      { field_id: "name", label: "Name", value: "Ada" },
      { field_id: "note", label: "Note", value: "two\nlines" },
    ]);
    expect(parseFormSubmission(content)).toEqual({
      label: "Contact",
      answers: [
        { label: "Name", value: "Ada" },
        { label: "Note", value: "two\nlines" },
      ],
    });
    expect(content).toContain('- note="two lines"');
  });
});

describe("consentDecisionContent", () => {
  it("reads back as the decision", () => {
    const card = { consent_id: "c1", title: 'Send "Hi"' } as ConsentRequest;
    const content = consentDecisionContent(card, { decision: "approve", always: true, edits: { text: "x" } });
    expect(parseConsentDecision(content)).toMatchObject({
      consentId: "c1",
      action: 'Send "Hi"',
      decision: "approved",
      edited: ["text"],
      always: true,
    });
  });
});
