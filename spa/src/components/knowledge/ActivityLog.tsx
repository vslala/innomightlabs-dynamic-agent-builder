import { useEffect, useRef } from "react";
import {
  Globe,
  FileText,
  Scissors,
  Brain,
  Database,
  CheckCircle,
  XCircle,
  AlertCircle,
  Loader2,
  Link,
  SkipForward,
  Play,
  Flag,
} from "lucide-react";
import { cn } from "../../lib/utils";
import type { CrawlEvent } from "../../types/knowledge";

interface ActivityLogProps {
  events: CrawlEvent[];
  maxHeight?: string;
  autoScroll?: boolean;
  className?: string;
}

const defaultEventConfig = {
  icon: AlertCircle,
  label: "Event",
  color: "text-gray-400",
  bgColor: "bg-gray-400/10",
};

const eventConfig: Record<
  string,
  {
    icon: React.ElementType;
    label: string;
    color: string;
    bgColor: string;
  }
> = {
  connected: {
    icon: CheckCircle,
    label: "Connected",
    color: "text-green-400",
    bgColor: "bg-green-400/10",
  },
  JOB_STARTED: {
    icon: Play,
    label: "Job Started",
    color: "text-blue-400",
    bgColor: "bg-blue-400/10",
  },
  JOB_PROGRESS: {
    icon: Loader2,
    label: "Progress Update",
    color: "text-blue-400",
    bgColor: "bg-blue-400/10",
  },
  JOB_CHECKPOINT: {
    icon: Flag,
    label: "Checkpoint Saved",
    color: "text-yellow-400",
    bgColor: "bg-yellow-400/10",
  },
  JOB_COMPLETED: {
    icon: CheckCircle,
    label: "Job Completed",
    color: "text-green-400",
    bgColor: "bg-green-400/10",
  },
  JOB_FAILED: {
    icon: XCircle,
    label: "Job Failed",
    color: "text-red-400",
    bgColor: "bg-red-400/10",
  },
  URL_DISCOVERED: {
    icon: Link,
    label: "URL Discovered",
    color: "text-cyan-400",
    bgColor: "bg-cyan-400/10",
  },
  URL_SKIPPED: {
    icon: SkipForward,
    label: "URL Skipped",
    color: "text-gray-400",
    bgColor: "bg-gray-400/10",
  },
  PAGE_FETCH_START: {
    icon: Globe,
    label: "Fetching Page",
    color: "text-purple-400",
    bgColor: "bg-purple-400/10",
  },
  PAGE_FETCH_COMPLETE: {
    icon: Globe,
    label: "Page Fetched",
    color: "text-purple-400",
    bgColor: "bg-purple-400/10",
  },
  PAGE_FETCH_ERROR: {
    icon: AlertCircle,
    label: "Fetch Error",
    color: "text-red-400",
    bgColor: "bg-red-400/10",
  },
  PAGE_PARSE_START: {
    icon: FileText,
    label: "Parsing Content",
    color: "text-orange-400",
    bgColor: "bg-orange-400/10",
  },
  PAGE_PARSE_COMPLETE: {
    icon: FileText,
    label: "Content Parsed",
    color: "text-orange-400",
    bgColor: "bg-orange-400/10",
  },
  PAGE_CHUNK_START: {
    icon: Scissors,
    label: "Chunking Content",
    color: "text-pink-400",
    bgColor: "bg-pink-400/10",
  },
  PAGE_CHUNK_COMPLETE: {
    icon: Scissors,
    label: "Content Chunked",
    color: "text-pink-400",
    bgColor: "bg-pink-400/10",
  },
  PAGE_EMBED_START: {
    icon: Brain,
    label: "Generating Embeddings",
    color: "text-indigo-400",
    bgColor: "bg-indigo-400/10",
  },
  PAGE_EMBED_COMPLETE: {
    icon: Brain,
    label: "Embeddings Generated",
    color: "text-indigo-400",
    bgColor: "bg-indigo-400/10",
  },
  PAGE_INGEST_START: {
    icon: Database,
    label: "Storing Vectors",
    color: "text-emerald-400",
    bgColor: "bg-emerald-400/10",
  },
  PAGE_INGEST_COMPLETE: {
    icon: Database,
    label: "Vectors Stored",
    color: "text-emerald-400",
    bgColor: "bg-emerald-400/10",
  },
  PAGE_ERROR: {
    icon: XCircle,
    label: "Page Error",
    color: "text-red-400",
    bgColor: "bg-red-400/10",
  },
};

function formatTimestamp(timestamp: string | undefined): string {
  if (!timestamp) return "";
  const date = new Date(timestamp);
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function truncateUrl(url: string, maxLength = 50): string {
  if (url.length <= maxLength) return url;
  const start = url.substring(0, maxLength - 15);
  const end = url.substring(url.length - 12);
  return `${start}...${end}`;
}

function ActivityLogItem({ event }: { event: CrawlEvent }) {
  const eventType = event.event_type || "unknown";
  const config = eventConfig[eventType] || defaultEventConfig;
  const Icon = config.icon;
  const isLoading = eventType.endsWith("_START");

  return (
    <div className="flex items-start gap-3 py-2 px-3 hover:bg-[var(--bg-tertiary)] rounded-md transition-colors">
      <div
        className={cn(
          "flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center",
          config.bgColor
        )}
      >
        <Icon
          className={cn(
            "h-4 w-4",
            config.color,
            isLoading && "animate-spin"
          )}
        />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className={cn("text-sm font-medium", config.color)}>
            {config.label}
          </span>
          {event.duration_ms !== undefined && event.duration_ms > 0 && (
            <span className="text-xs text-[var(--text-muted)]">
              {event.duration_ms}ms
            </span>
          )}
          <span className="text-xs text-[var(--text-muted)] ml-auto">
            {formatTimestamp(event.timestamp)}
          </span>
        </div>
        {event.url && (
          <p className="text-xs text-[var(--text-muted)] truncate mt-0.5">
            {truncateUrl(event.url)}
          </p>
        )}
        {event.error_message && (
          <p className="text-xs text-red-400 mt-0.5">{event.error_message}</p>
        )}
        {event.details && Object.keys(event.details).length > 0 && (
          <p className="text-xs text-[var(--text-muted)] mt-0.5">
            {Object.entries(event.details)
              .map(([k, v]) => `${k}: ${v}`)
              .join(" | ")}
          </p>
        )}
      </div>
    </div>
  );
}

export function ActivityLog({
  events,
  maxHeight = "400px",
  autoScroll = true,
  className,
}: ActivityLogProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events, autoScroll]);

  if (events.length === 0) {
    return (
      <div
        className={cn(
          "flex items-center justify-center py-8 text-[var(--text-muted)]",
          className
        )}
      >
        <Loader2 className="h-5 w-5 mr-2 animate-spin" />
        <span>Waiting for events...</span>
      </div>
    );
  }

  return (
    <div
      ref={scrollRef}
      className={cn(
        "overflow-y-auto scrollbar-thin scrollbar-thumb-[var(--border-subtle)] scrollbar-track-transparent",
        className
      )}
      style={{ maxHeight }}
    >
      <div className="space-y-1">
        {events.map((event, index) => (
          <ActivityLogItem key={event.step_id || index} event={event} />
        ))}
      </div>
    </div>
  );
}

export function ActivityLogHeader({
  eventCount,
  isStreaming,
}: {
  eventCount: number;
  isStreaming: boolean;
}) {
  return (
    <div className="flex items-center justify-between">
      <h3 className="text-sm font-medium text-[var(--text-primary)]">
        Activity Log
      </h3>
      <div className="flex items-center gap-2">
        {isStreaming && (
          <span className="flex items-center gap-1.5 text-xs text-green-400">
            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            Live
          </span>
        )}
        <span className="text-xs text-[var(--text-muted)]">
          {eventCount} events
        </span>
      </div>
    </div>
  );
}
