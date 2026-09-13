/**
 * Optional smart-value support for schema forms.
 *
 * A form only gains the `{{` picker when something above it provides a catalog.
 * Every other SchemaForm in the app is unaffected, so this stays a capability
 * the automation workspace opts into rather than a change to all forms.
 */

import { createContext, useContext } from "react";

export interface SmartValueSuggestion {
  path: string;
  label: string;
  description?: string;
  /** Resolved value from the selected run, when there is one. */
  sample?: string;
}

export interface SmartValueSuggestionGroup {
  id: string;
  label: string;
  subtitle?: string;
  fields: SmartValueSuggestion[];
}

/** A field that can receive a token from outside, e.g. from a run output tree. */
export interface SmartValueTarget {
  id: string;
  label: string;
  insert: (token: string) => void;
}

export interface SmartValueContextValue {
  groups: SmartValueSuggestionGroup[];
  /** Renders a template server-side against a run, for an exact preview. */
  preview?: (template: string) => Promise<string>;
  /** The field that last had focus, which external inserts write into. */
  getTarget: () => SmartValueTarget | null;
  setTarget: (target: SmartValueTarget) => void;
  clearTarget: (id: string) => void;
}

export const SmartValueContext = createContext<SmartValueContextValue | null>(null);

export function useOptionalSmartValues(): SmartValueContextValue | null {
  return useContext(SmartValueContext);
}

export function fieldWantsSmartValues(attr: Record<string, string> | null | undefined): boolean {
  return attr?.smart_values === "true";
}

export function findSuggestion(
  groups: SmartValueSuggestionGroup[],
  path: string
): SmartValueSuggestion | null {
  for (const group of groups) {
    const match = group.fields.find((field) => field.path === path);
    if (match) return match;
  }
  return null;
}
