/**
 * Query-string state for the workspace: which step is expanded, which panel is
 * open, which run is selected.
 *
 * `useSearchParams` cannot be used directly for this. Its setter closes over the
 * params from the render that created it, so two writes before the next commit
 * silently discard each other's keys, and its identity changes on every URL
 * change, which makes any effect that depends on it re-run constantly. Both add
 * up to dropped params and navigation loops.
 *
 * This hook writes through refs instead: `update` is stable for the lifetime of
 * the component, always reads the live URL, and never navigates when the patch
 * would not change anything.
 */

import { useCallback, useEffect, useMemo, useRef } from "react";
import { useSearchParams } from "react-router-dom";

export type WorkspaceParamKey = "step" | "panel" | "run" | "focus";

export type WorkspaceParamPatch = Partial<Record<WorkspaceParamKey, string | null>>;

export interface WorkspaceParams {
  step: string | null;
  panel: string | null;
  run: string | null;
  focus: string | null;
  /** Apply several keys in one navigation. Stable across renders. */
  update: (patch: WorkspaceParamPatch) => void;
}

export function useWorkspaceParams(): WorkspaceParams {
  const [search, setSearch] = useSearchParams();

  const searchRef = useRef(search);
  const setSearchRef = useRef(setSearch);

  // Synced after commit, which is before any event handler or later effect can
  // call `update`, so it always writes against the live URL.
  useEffect(() => {
    searchRef.current = search;
    setSearchRef.current = setSearch;
  }, [search, setSearch]);

  const update = useCallback((patch: WorkspaceParamPatch) => {
    const next = applyParamPatch(searchRef.current, patch);
    if (next === null) return;
    setSearchRef.current(next, { replace: true });
  }, []);

  return useMemo(
    () => ({
      step: search.get("step"),
      panel: search.get("panel"),
      run: search.get("run"),
      focus: search.get("focus"),
      update,
    }),
    [search, update]
  );
}

/**
 * Merge a patch into the current params, or return null when nothing changes.
 *
 * Returning null is what stops a redundant navigation, and with it any loop
 * between two effects that each insist on their own key.
 */
export function applyParamPatch(
  current: URLSearchParams,
  patch: WorkspaceParamPatch
): URLSearchParams | null {
  const next = new URLSearchParams(current);
  let changed = false;

  for (const [key, value] of Object.entries(patch)) {
    const existing = next.get(key);
    if (value === null || value === "") {
      if (existing !== null) {
        next.delete(key);
        changed = true;
      }
      continue;
    }
    if (existing !== value) {
      next.set(key, value);
      changed = true;
    }
  }

  return changed ? next : null;
}
