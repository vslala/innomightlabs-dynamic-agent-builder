import { useCallback, useEffect, useState } from "react";
import { Gauge } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../ui/tooltip";
import { tokenUsageApiService, type TokenUsagePoint } from "../../services/tokenUsage";
import { formatCompactNumber } from "../../lib/utils";
import styles from "./TokenUsageIndicator.module.css";

export interface LiveTokenUsageUpdate {
  llm_model: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  call_count: number;
}

interface TokenUsageIndicatorProps {
  agentId?: string;
  /** Latest per-model "today" totals pushed from an SSE token_usage event.
   * Pass a new object on every event -- it's merged into local state by
   * llm_model, keeping the indicator current without waiting on a refetch. */
  liveUsage?: LiveTokenUsageUpdate | null;
}

function startOfTodayUtc(): Date {
  const date = new Date();
  date.setUTCHours(0, 0, 0, 0);
  return date;
}

function mergeLiveUsage(
  series: TokenUsagePoint[] | null,
  liveUsage: LiveTokenUsageUpdate | null | undefined
): TokenUsagePoint[] | null {
  if (!liveUsage) return series;

  const base = series ?? [];
  const index = base.findIndex((point) => point.llm_model === liveUsage.llm_model);
  const nextPoint: TokenUsagePoint = {
    period_key: base[index]?.period_key ?? startOfTodayUtc().toISOString().slice(0, 10),
    period_start: base[index]?.period_start ?? startOfTodayUtc().toISOString(),
    llm_model: liveUsage.llm_model,
    prompt_tokens: liveUsage.prompt_tokens,
    completion_tokens: liveUsage.completion_tokens,
    total_tokens: liveUsage.total_tokens,
    call_count: liveUsage.call_count,
  };

  if (index === -1) return [...base, nextPoint];
  const next = [...base];
  next[index] = nextPoint;
  return next;
}

export function TokenUsageIndicator({ agentId, liveUsage }: TokenUsageIndicatorProps) {
  const [series, setSeries] = useState<TokenUsagePoint[] | null>(null);

  const fetchUsage = useCallback(() => {
    if (!agentId) return;
    tokenUsageApiService
      .getTokenUsage(agentId, {
        period: "day",
        from: startOfTodayUtc().toISOString(),
        to: new Date().toISOString(),
      })
      .then((response) => setSeries(response.series))
      .catch(() => setSeries(null));
  }, [agentId]);

  useEffect(() => {
    fetchUsage();
  }, [fetchUsage]);

  // Merge the latest live SSE delta into the fetched baseline at render time
  // -- a pure derivation, not a side effect, so no second state/effect needed.
  const displaySeries = mergeLiveUsage(series, liveUsage);

  if (!agentId || !displaySeries || displaySeries.length === 0) {
    return null;
  }

  const totalTokens = displaySeries.reduce((sum, point) => sum + point.total_tokens, 0);
  if (totalTokens === 0) {
    return null;
  }

  const byModel = [...displaySeries].sort((a, b) => b.total_tokens - a.total_tokens);

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip onOpenChange={(open) => open && fetchUsage()}>
        <TooltipTrigger asChild>
          <span className={styles.indicator} aria-label={`Tokens consumed today: ${totalTokens}`}>
            <Gauge className={styles.icon} />
            <span>{formatCompactNumber(totalTokens)} today</span>
          </span>
        </TooltipTrigger>
        <TooltipContent>
          <div className={styles.tooltipTitle}>Token usage today</div>
          {byModel.map((point) => (
            <div key={point.llm_model} className={styles.tooltipRow}>
              <span className={styles.tooltipModel}>{point.llm_model}</span>
              <span className={styles.tooltipValue}>{formatCompactNumber(point.total_tokens)}</span>
            </div>
          ))}
          <div className={styles.tooltipDivider} />
          <div className={styles.tooltipRow}>
            <span className={styles.tooltipModel}>Total</span>
            <span className={styles.tooltipValue}>{formatCompactNumber(totalTokens)}</span>
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
