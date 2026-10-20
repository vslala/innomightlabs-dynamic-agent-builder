import { useEffect, useRef, useState, type FormEvent } from "react";
import { Search } from "lucide-react";
import { AlertBanner, Button, LoadingState, SearchInput } from "../../../components/ui";
import { knowledgeApiService } from "../../../services/knowledge";
import type { KnowledgePage, SearchResult } from "../../../types/knowledge";
import { askVerdict } from "./knowledgeWorkspace";
import styles from "./KnowledgeAsk.module.css";

const RESULTS = 5;
const EXAMPLES = 3;

interface KnowledgeAskProps {
  kbId: string;
  pages: KnowledgePage[] | null;
  /** A question to run as soon as it arrives (from "Ask about this" in the reader); `at` makes a repeat count. */
  request: { question: string; at: number } | null;
  /** Open the page a result came from, at that chunk. */
  onOpenResult: (url: string, chunkId: string) => void;
}

function scoreClass(score: number): string {
  if (score >= 0.6) return styles.scoreGood;
  return score >= 0.4 ? styles.scoreWeak : styles.scorePoor;
}

/** Ask what an agent would ask, and see which chunks come back from which pages, and how well they match. */
export function KnowledgeAsk({ kbId, pages, request, onOpenResult }: KnowledgeAskProps) {
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState<{ question: string; results: SearchResult[] } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);

  const run = async (text: string) => {
    const query = text.trim();
    if (!query) return;
    const mine = ++latest.current;
    setQuestion(query);
    setLoading(true);
    setError(null);
    try {
      const response = await knowledgeApiService.searchKnowledgeBase(kbId, query, RESULTS);
      if (mine === latest.current) setAsked({ question: query, results: response.results });
    } catch (err) {
      if (mine === latest.current) setError(err instanceof Error ? err.message : "The search failed. Try again.");
    } finally {
      if (mine === latest.current) setLoading(false);
    }
  };

  useEffect(() => {
    if (request) void run(request.question);
    // run is rebuilt each render; only a new request should trigger it
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void run(question);
  };

  const examples = (pages ?? []).filter((page) => page.state === "live" && page.title).slice(0, EXAMPLES);
  const verdict = asked ? askVerdict(asked.results) : null;

  return (
    <div className={styles.ask}>
      <h2 className={styles.heading}>Ask it what your agents would ask</h2>
      <p className={styles.lead}>
        See which chunks come back, from which pages, and how well they match. If the right page is missing or ranks low,
        you'll see it here before a customer does.
      </p>

      <form className={styles.form} onSubmit={submit}>
        <SearchInput
          placeholder="e.g. How do I connect Slack to an agent?"
          aria-label="Question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
        />
        <Button type="submit" disabled={loading || !question.trim()}>
          <Search className="h-4 w-4" />
          Search
        </Button>
      </form>

      {examples.length > 0 && (
        <div className={styles.examples}>
          <span>Try:</span>
          {examples.map((page) => (
            <Button key={page.url} variant="outline" size="sm" onClick={() => run(`What is ${page.title}?`)}>
              What is {page.title}?
            </Button>
          ))}
        </div>
      )}

      {error && <AlertBanner message={error} variant="error" />}
      {loading && <LoadingState className={styles.loading} size="default" />}

      {!loading && asked && verdict && (
        <div className={styles.answers} aria-live="polite">
          {verdict === "good" && (
            <p className={`${styles.verdict} ${styles.verdictGood}`}>
              Good match. The top chunk comes from <b>{asked.results[0].page_title || asked.results[0].source_url}</b>.
            </p>
          )}
          {verdict === "weak" && (
            <p className={`${styles.verdict} ${styles.verdictWeak}`}>
              <b>A partial match.</b> The best chunk only loosely fits. An agent may answer vaguely or from the wrong page.
            </p>
          )}
          {verdict === "none" && (
            <p className={`${styles.verdict} ${styles.verdictNone}`}>
              <b>No page answers this well.</b> An agent would likely say it doesn't know, or guess. Add the missing page by
              crawling it or uploading a file.
            </p>
          )}
          <ol className={styles.hits}>
            {asked.results.map((result) => (
              <li key={result.chunk_id} className={`${styles.hit} ${result.score < 0.4 ? styles.hitFaint : ""}`}>
                <div className={`${styles.score} ${scoreClass(result.score)}`}>
                  {Math.round(result.score * 100)}
                  <small>match</small>
                </div>
                <div className={styles.hitBody}>
                  <Button variant="link" size="sm" className={styles.where} onClick={() => onOpenResult(result.source_url, result.chunk_id)}>
                    {result.page_title || result.source_url}
                  </Button>
                  <p>{result.content}</p>
                </div>
              </li>
            ))}
          </ol>
          {asked.results.length === 0 && <p className={styles.lead}>Nothing in this knowledge base is close to that.</p>}
        </div>
      )}
    </div>
  );
}
