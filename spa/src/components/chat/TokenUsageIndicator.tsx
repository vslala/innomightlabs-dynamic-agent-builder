import { useEffect, useState } from "react";
import { Gauge } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../ui/tooltip";
import { tokenUsageApiService, type TokenUsagePoint } from "../../services/tokenUsage";
import { formatCompactNumber } from "../../lib/utils";
import styles from "./TokenUsageIndicator.module.css";

interface TokenUsageIndicatorProps {
  agentId?: string;
}

function startOfTodayUtc(): Date {
  const date = new Date();
  date.setUTCHours(0, 0, 0, 0);
  return date;
}

export function TokenUsageIndicator({ agentId }: TokenUsageIndicatorProps) {
  const [series, setSeries] = useState<TokenUsagePoint[] | null>(null);

  useEffect(() => {
    if (!agentId) {
      return;
    }

    let cancelled = false;
    tokenUsageApiService
      .getTokenUsage(agentId, {
        period: "day",
        from: startOfTodayUtc().toISOString(),
        to: new Date().toISOString(),
      })
      .then((response) => {
        if (!cancelled) setSeries(response.series);
      })
      .catch(() => {
        if (!cancelled) setSeries(null);
      });

    return () => {
      cancelled = true;
    };
  }, [agentId]);

  if (!agentId || !series || series.length === 0) {
    return null;
  }

  const totalTokens = series.reduce((sum, point) => sum + point.total_tokens, 0);
  if (totalTokens === 0) {
    return null;
  }

  const byModel = [...series].sort((a, b) => b.total_tokens - a.total_tokens);

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
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
