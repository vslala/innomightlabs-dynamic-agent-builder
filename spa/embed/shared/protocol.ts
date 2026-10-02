/**
 * The contract between the `embed.js` loader (on the customer's page) and the
 * chat app inside the iframe. Both sides import this file, so they can't drift.
 *
 * Configuration travels once, in the iframe URL's #fragment (never sent to a
 * server). Runtime messages travel over postMessage, wrapped in a versioned
 * envelope so unrelated messages on the page are ignored.
 */

export const MESSAGE_SOURCE = "innomight-embed";
export const PROTOCOL_VERSION = 1;

export type EmbedMode = "floating" | "inline";
export type EmbedTheme = "light" | "dark" | "auto";

export interface EmbedConfig {
  mode: EmbedMode;
  theme: EmbedTheme;
  primaryColor?: string;
  greeting?: string;
  placeholder?: string;
  /** Sent for the visitor as soon as the chat is first seen, so the agent answers about that part of the page right away. */
  prompt?: string;
  /** Shown in the visitor's bubble instead of the full prompt. */
  promptLabel?: string;
  /** `false` offers the prompt as a one-click suggestion instead of sending it when the chat is seen. Default `true`. */
  autoPrompt?: boolean;
}

export type HostToFrameMessage = { type: "open" } | { type: "close" };

export type FrameToHostMessage = { type: "ready" } | { type: "close" };

type Envelope<T> = T & { source: typeof MESSAGE_SOURCE; v: typeof PROTOCOL_VERSION };

export function envelope<T extends { type: string }>(message: T): Envelope<T> {
  return { ...message, source: MESSAGE_SOURCE, v: PROTOCOL_VERSION };
}

export function isEmbedMessage(data: unknown): data is Envelope<{ type: string }> {
  if (!data || typeof data !== "object") return false;
  const candidate = data as Record<string, unknown>;
  return candidate.source === MESSAGE_SOURCE && candidate.v === PROTOCOL_VERSION && typeof candidate.type === "string";
}

const DEFAULT_CONFIG: EmbedConfig = { mode: "floating", theme: "auto" };

export function encodeConfig(config: EmbedConfig): string {
  return encodeURIComponent(JSON.stringify(config));
}

/** Reads the config from a URL fragment, falling back to defaults for anything missing or malformed. */
export function decodeConfig(fragment: string): EmbedConfig {
  try {
    const parsed = JSON.parse(decodeURIComponent(fragment.replace(/^#/, ""))) as Partial<EmbedConfig>;
    return {
      ...DEFAULT_CONFIG,
      ...parsed,
      mode: parsed.mode === "inline" ? "inline" : "floating",
      theme: parsed.theme === "light" || parsed.theme === "dark" ? parsed.theme : "auto",
    };
  } catch {
    return DEFAULT_CONFIG;
  }
}
