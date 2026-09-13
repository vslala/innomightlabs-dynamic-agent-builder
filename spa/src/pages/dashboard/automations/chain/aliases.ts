/**
 * Client-side mirror of the alias rules in api/src/automations/aliases.py.
 *
 * Aliases are validated on every save, so the editor shapes what the user types
 * into a legal reference name instead of letting each keystroke fail.
 */

export const RESERVED_ALIASES = new Set([
  "current",
  "env",
  "execution",
  "input",
  "last",
  "nodes",
  "run",
  "steps",
  "trigger",
]);

const MAX_ALIAS_LENGTH = 63;

/**
 * Coerce typed text into a legal alias.
 *
 * Trailing underscores are kept so that typing a space mid-word does not get
 * swallowed; the backend accepts them.
 */
export function slugifyAliasInput(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, "_")
    .replace(/_{2,}/g, "_")
    .replace(/^[^a-z]+/, "")
    .slice(0, MAX_ALIAS_LENGTH);
}

export function aliasError(alias: string): string | null {
  if (!alias) return null;
  if (RESERVED_ALIASES.has(alias)) {
    return `"${alias}" is reserved. Try something like ${alias}_step.`;
  }
  return null;
}
