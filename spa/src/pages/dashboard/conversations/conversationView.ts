import { platform } from "../../../platform";

/** Which way the conversations are shown: the turning cloud, or the original list with its sidebar. */
export type ConversationView = "cloud" | "classic";

/** Anything but a saved "classic" (nothing saved, something stale or odd) means the cloud. */
export function parseView(saved: string | null): ConversationView {
  return saved === "classic" ? "classic" : "cloud";
}

/** Blocked storage (private mode, embedded frames) reads as nothing saved; the platform tolerates it. */
export function loadView(): ConversationView {
  return parseView(platform().storage.get("conversations:view"));
}

export function saveView(view: ConversationView): void {
  platform().storage.set("conversations:view", view);
}
