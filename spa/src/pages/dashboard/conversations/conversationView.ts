/** Which way the conversations are shown: the turning cloud, or the original list with its sidebar. */
export type ConversationView = "cloud" | "classic";

const STORAGE_KEY = "conversations:view";

/** Anything but a saved "classic" (nothing saved, something stale or odd) means the cloud. */
export function parseView(saved: string | null): ConversationView {
  return saved === "classic" ? "classic" : "cloud";
}

export function loadView(): ConversationView {
  try {
    return parseView(localStorage.getItem(STORAGE_KEY));
  } catch {
    return "cloud"; // storage can be blocked (private mode, embedded frames)
  }
}

export function saveView(view: ConversationView): void {
  try {
    localStorage.setItem(STORAGE_KEY, view);
  } catch {
    // The choice just won't be remembered.
  }
}
