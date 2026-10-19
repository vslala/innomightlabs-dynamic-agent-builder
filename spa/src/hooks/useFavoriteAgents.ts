import { useCallback, useState } from "react";
import { authService } from "../services/auth";

function storageKey(): string {
  return `innomight.favorite-agents.${authService.getUserFromToken()?.userId ?? "anonymous"}`;
}

function load(): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(storageKey()) ?? "[]") as string[]);
  } catch {
    return new Set();
  }
}

/** The agent ids this person starred. Kept in this browser; ids of deleted agents are simply never shown. */
export function useFavoriteAgents(): { favorites: Set<string>; toggleFavorite: (agentId: string) => void } {
  const [favorites, setFavorites] = useState(load);

  const toggleFavorite = useCallback((agentId: string) => {
    setFavorites((current) => {
      const next = new Set(current);
      if (!next.delete(agentId)) next.add(agentId);
      localStorage.setItem(storageKey(), JSON.stringify([...next]));
      return next;
    });
  }, []);

  return { favorites, toggleFavorite };
}
