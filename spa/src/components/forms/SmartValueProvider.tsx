import { useCallback, useMemo, useRef, type ReactNode } from "react";

import {
  SmartValueContext,
  type SmartValueContextValue,
  type SmartValueSuggestionGroup,
  type SmartValueTarget,
} from "./SmartValueContext";

/**
 * Supplies a smart-value catalog to the schema form beneath it.
 *
 * Also remembers which field last had focus, so a value picked from somewhere
 * else on screen -- a run output tree, for instance -- knows where to land.
 */
export function SmartValueProvider({
  groups,
  preview,
  children,
}: {
  groups: SmartValueSuggestionGroup[];
  preview?: (template: string) => Promise<string>;
  children: ReactNode;
}) {
  const targetRef = useRef<SmartValueTarget | null>(null);

  const setTarget = useCallback((target: SmartValueTarget) => {
    targetRef.current = target;
  }, []);

  const clearTarget = useCallback((id: string) => {
    if (targetRef.current?.id === id) targetRef.current = null;
  }, []);

  const getTarget = useCallback(() => targetRef.current, []);

  const value = useMemo<SmartValueContextValue>(
    () => ({ groups, preview, getTarget, setTarget, clearTarget }),
    [clearTarget, getTarget, groups, preview, setTarget]
  );

  return <SmartValueContext.Provider value={value}>{children}</SmartValueContext.Provider>;
}
