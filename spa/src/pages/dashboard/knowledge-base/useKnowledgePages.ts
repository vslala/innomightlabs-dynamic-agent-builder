import { useEffect, useState } from "react";
import { knowledgeApiService } from "../../../services/knowledge";
import type { KnowledgePage } from "../../../types/knowledge";

const REQUEST_SIZE = 100;
/** The most pages loaded at once; a knowledge base with more is searched by title or address on the server. */
const MAX_PAGES = 1000;

export interface KnowledgePages {
  /** None until the first load; kept while a reload is under way so the list doesn't flash. */
  pages: KnowledgePage[] | null;
  /** The knowledge base has more pages than were loaded. */
  truncated: boolean;
  error: string | null;
}

/** Every page of the knowledge base as it is now, reloaded when `refreshKey` changes (a crawl started or ended). */
export function useKnowledgePages(kbId: string, refreshKey: string): KnowledgePages {
  const [state, setState] = useState<KnowledgePages>({ pages: null, truncated: false, error: null });

  useEffect(() => {
    let current = true;
    (async () => {
      const loaded: KnowledgePage[] = [];
      let cursor: string | null = null;
      do {
        const batch = await knowledgeApiService.listPages(kbId, { limit: REQUEST_SIZE, cursor });
        loaded.push(...batch.items);
        cursor = batch.next_cursor;
      } while (cursor && loaded.length < MAX_PAGES);
      if (current) setState({ pages: loaded, truncated: cursor !== null, error: null });
    })().catch((err: unknown) => {
      if (current) {
        setState((previous) => ({ ...previous, error: err instanceof Error ? err.message : "Couldn't load the pages" }));
      }
    });
    return () => {
      current = false;
    };
  }, [kbId, refreshKey]);

  return state;
}
