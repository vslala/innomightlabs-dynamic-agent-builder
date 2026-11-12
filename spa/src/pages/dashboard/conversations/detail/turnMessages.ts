import type { FormAnswer } from "../../../../components/chat/ChatFormRenderer";
import type { LiveTokenUsageUpdate } from "../../../../components/chat/TokenUsageIndicator";
import type { ConsentDecision, ConsentRequest } from "../../../../types/consent";
import type { GeneratedImageResponse, Message, MessageForm, SSEEvent } from "../../../../types/message";

/** The day's token totals a TOKEN_USAGE_UPDATE carries, or null when it names no model. */
export function liveTokenUsageFrom(event: SSEEvent): LiveTokenUsageUpdate | null {
  if (!event.llm_model) return null;
  return {
    llm_model: event.llm_model,
    prompt_tokens: event.prompt_tokens ?? 0,
    completion_tokens: event.completion_tokens ?? 0,
    total_tokens: event.total_tokens ?? 0,
    call_count: event.call_count ?? 0,
  };
}

/** The partial picture an IMAGE_GENERATION_PARTIAL carries, as a data URL. */
export function partialImageDataUrl(event: SSEEvent): string | null {
  if (!event.image_b64) return null;
  return `data:${event.image_mime_type || "image/png"};base64,${event.image_b64}`;
}

interface GeneratedImageMessageInput {
  messageId: string;
  conversationId: string;
  prompt: string;
  images: GeneratedImageResponse[];
  /** The last partial preview, shown until the stored image has loaded. */
  previewDataUrl: string | null;
}

/** The assistant message for finished images, shaped like the one the API saves. */
export function generatedImageMessage({
  messageId,
  conversationId,
  prompt,
  images,
  previewDataUrl,
}: GeneratedImageMessageInput): Message {
  const label = prompt || "Generated image";
  return {
    message_id: messageId,
    conversation_id: conversationId,
    role: "assistant",
    content: `Generated image: ${label}`,
    images: images.map((image) => ({
      image_id: image.image_id,
      url: image.url,
      preview_data_url: previewDataUrl,
      filename: image.filename,
      mime_type: image.mime_type,
      size_bytes: image.size_bytes,
      width: image.width,
      height: image.height,
      prompt: image.prompt,
      revised_prompt: image.revised_prompt,
    })),
    created_at: new Date().toISOString(),
  };
}

/** Adds a message unless one with its id is already there: live events and recovery can both deliver it. */
export function appendOnce(messages: Message[], message: Message): Message[] {
  return messages.some((each) => each.message_id === message.message_id) ? messages : [...messages, message];
}

/**
 * The transcript after a resync: the newest page from the server (oldest first) appended where it is new.
 * Optimistic `temp-` messages go, because the page holds their saved copies. Unchanged input comes back as is.
 */
export function mergeLatestPage(current: Message[], latest: Message[]): Message[] {
  const saved = current.filter((message) => !message.message_id.startsWith("temp-"));
  const known = new Set(saved.map((message) => message.message_id));
  const arrived = latest.filter((message) => !known.has(message.message_id));
  if (arrived.length === 0 && saved.length === current.length) return current;
  return [...saved, ...arrived];
}

/**
 * The form still waiting for the person when a chat is opened: the one the latest message asked, if that message
 * is the assistant's. A reply of any kind spends it (a plan's approval is checked against the latest message).
 */
export function formAwaitingAnswer(messages: Message[]): MessageForm | null {
  const latest = messages[messages.length - 1];
  return latest?.role === "assistant" && latest.form ? latest.form : null;
}

/**
 * What a submitted chat form sends: a readable block the transcript shows as a card (see submittedFormParser),
 * then the field ids the agent matches against the form it asked.
 */
export function formSubmissionContent(label: string, answers: FormAnswer[]): string {
  return [
    `<form_submission label="${label}">`,
    ...answers.map((answer) => `- ${answer.label}: ${answer.value.replace(/\n/g, "\\n")}`),
    "</form_submission>",
    "",
    "Fields:",
    ...answers.map((answer) => `- ${answer.field_id}="${answer.value.replace(/\n/g, " ")}"`),
  ].join("\n");
}

/** The line the API saves for a decision on a consent card, so the optimistic message reads the same until it arrives. */
export function consentDecisionContent(card: ConsentRequest, decision: ConsentDecision): string {
  const edited = Object.keys(decision.edits ?? {});
  return (
    `<consent_decision consent_id="${card.consent_id}" action=${JSON.stringify(card.title)} ` +
    `decision="${decision.decision === "approve" ? "approved" : "rejected"}"` +
    `${edited.length ? ` edited="${edited.join(",")}"` : ""}${decision.always ? ' always="true"' : ""}>\n</consent_decision>`
  );
}
