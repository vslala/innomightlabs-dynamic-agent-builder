/**
 * Pure token handling for smart value fields: what is in the text, where the
 * caret is inside a token, and what a chosen value should replace.
 *
 * Kept out of the component so the caret rules can be tested directly.
 */

import type { SmartValueSuggestionGroup } from "./SmartValueContext";

const TOKEN_PATTERN = /\{\{(.*?)\}\}/g;

export function tokenFor(path: string): string {
  return `{{ ${path} }}`;
}

/** Resolver paths referenced by the text, with any filter suffix dropped. */
export function parseTokenPaths(text: string): string[] {
  if (!text) return [];
  const paths: string[] = [];
  TOKEN_PATTERN.lastIndex = 0;
  let match = TOKEN_PATTERN.exec(text);
  while (match) {
    const path = match[1].trim().split("|")[0].trim();
    if (path) paths.push(path);
    match = TOKEN_PATTERN.exec(text);
  }
  return paths;
}

/**
 * What has been typed after an unclosed `{{`, or null when the caret is not
 * inside a token. That string is the picker's filter.
 */
export function openTokenQuery(before: string): string | null {
  const open = before.lastIndexOf("{{");
  if (open === -1) return null;
  const after = before.slice(open + 2);
  if (after.includes("}}")) return null;
  return after.trimStart();
}

/**
 * Insert a token over the selection.
 *
 * A half-typed `{{ ste` is what opened the picker, so it is replaced rather
 * than left in front of the inserted token.
 */
export function insertTokenAt(
  text: string,
  selectionStart: number,
  selectionEnd: number,
  token: string
): { value: string; cursor: number } {
  const before = text.slice(0, selectionStart);
  const open = before.lastIndexOf("{{");
  const trimmed =
    open !== -1 && !before.slice(open + 2).includes("}}") ? before.slice(0, open) : before;
  return {
    value: `${trimmed}${token}${text.slice(selectionEnd)}`,
    cursor: trimmed.length + token.length,
  };
}

/** True when a path matches no catalog entry and no catalog root. */
export function isUnknownPath(path: string, groups: SmartValueSuggestionGroup[]): boolean {
  if (!path) return true;
  // Legacy `$.` paths still resolve server-side, so they are never flagged.
  if (path.startsWith("$.")) return false;
  const root = rootOf(path);
  return !groups.some((group) =>
    group.fields.some((field) => field.path === path || rootOf(field.path) === root)
  );
}

function rootOf(path: string): string {
  return path.split(".").slice(0, 2).join(".");
}
