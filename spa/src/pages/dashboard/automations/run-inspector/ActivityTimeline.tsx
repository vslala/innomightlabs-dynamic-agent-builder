/**
 * Every move an agent step made, in the order the agent made it: the prompt it was given, each tool call, and
 * its reply. Searchable and filterable; selecting a call opens it in full beside the list on wide screens and
 * in a bottom sheet on phones, with previous/next to walk the run without going back to the list.
 */

import { useEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";
import { ChevronLeft, ChevronRight, MessageSquareReply, MessageSquareText } from "lucide-react";

import {
  Button,
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  SearchInput,
  Spinner,
  Toggle,
} from "../../../../components/ui";
import { formatClockTime, formatMs } from "../components/runStatus";
import { ToolCallBadge, ToolCallDetail } from "./ToolCallDetail";
import {
  argumentSummary,
  durationMs,
  matchesFilter,
  matchesQuery,
  toolCallTitle,
  toolCounts,
  type ToolCall,
  type ToolCallFilter,
} from "./toolCalls";
import type { StepToolCalls } from "./useStepToolCalls";

/** Wide enough for the list and the selected call side by side. Matches `run-activity` in run-inspector.css. */
const SIDE_BY_SIDE_PX = 736;

export function ActivityTimeline({
  toolCalls,
  prompt,
  reply,
  selectedCallId,
  onSelectCall,
  onShowInput,
  onShowOutput,
}: {
  toolCalls: StepToolCalls;
  prompt: string | null;
  reply: string | null;
  selectedCallId: string | null;
  onSelectCall: (callId: string | null) => void;
  onShowInput: () => void;
  onShowOutput: () => void;
}) {
  const root = useRef<HTMLDivElement>(null);
  const sideBySide = useWidthAtLeast(root, SIDE_BY_SIDE_PX);
  const [filter, setFilter] = useState<ToolCallFilter>({ kind: "all" });
  const [query, setQuery] = useState("");
  const { calls, loading, error, retry } = toolCalls;

  const visible = useMemo(
    () => calls.filter((call) => matchesFilter(call, filter) && matchesQuery(call, query)),
    [calls, filter, query]
  );
  const selectedIndex = visible.findIndex((call) => call.id === selectedCallId);
  const selected = selectedIndex === -1 ? null : visible[selectedIndex];
  const unfiltered = filter.kind === "all" && !query.trim();
  const clearFilters = () => {
    setFilter({ kind: "all" });
    setQuery("");
  };

  // The root always renders, so its width is known by the time the calls arrive
  if (loading || error) {
    return (
      <div className="run-inspector-activity" ref={root}>
        {loading ? (
          <div className="run-inspector-empty">
            <Spinner size="sm" />
            <span>Loading this step's activity…</span>
          </div>
        ) : (
          <div className="run-inspector-empty" role="alert">
            <span>{error}</span>
            <Button variant="outline" size="sm" onClick={retry}>
              Try again
            </Button>
          </div>
        )}
      </div>
    );
  }

  const pager = selected ? (
    <Pager index={selectedIndex} count={visible.length} onMove={(next) => onSelectCall(visible[next].id)} />
  ) : null;

  return (
    <div className="run-inspector-activity" ref={root}>
      <SearchInput
        aria-label="Search tool calls"
        placeholder="Search tools, arguments and responses"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <FilterChips calls={calls} filter={filter} onChange={setFilter} />

      <div className="run-inspector-activity__split">
        <ol className="run-inspector-timeline" aria-label="Agent activity, in order">
          {unfiltered && prompt !== null && (
            <EdgeRow icon={<MessageSquareText className="h-4 w-4" />} title="Prompt sent to the agent" detail={prompt} onClick={onShowInput} />
          )}
          {visible.map((call) => (
            <CallRow
              key={call.id}
              call={call}
              selected={call.id === selectedCallId}
              onClick={() => onSelectCall(call.id === selectedCallId && sideBySide ? null : call.id)}
            />
          ))}
          {visible.length === 0 && (
            <li className="run-inspector-empty">
              <span>{calls.length === 0 ? "The agent answered without calling any tools." : "No tool calls match."}</span>
              {calls.length > 0 && (
                <Button variant="ghost" size="sm" onClick={clearFilters}>
                  Clear filters
                </Button>
              )}
            </li>
          )}
          {unfiltered && reply !== null && (
            <EdgeRow icon={<MessageSquareReply className="h-4 w-4" />} title="Agent replied" detail={reply} onClick={onShowOutput} />
          )}
        </ol>

        {sideBySide && (
          <aside className="run-inspector-activity__pane" aria-label="Selected tool call">
            {selected ? (
              <>
                <ToolCallDetail call={selected} total={calls.length} />
                {pager}
              </>
            ) : (
              <p className="run-inspector-muted">Select a tool call to see its arguments and response in full.</p>
            )}
          </aside>
        )}
      </div>

      {!sideBySide && (
        <Dialog open={selected !== null} onOpenChange={(open) => (open ? undefined : onSelectCall(null))}>
          <DialogContent className="run-inspector-sheet">
            <DialogHeader>
              <DialogTitle>
                Tool call {selected?.sequence} of {calls.length}
              </DialogTitle>
              <DialogDescription className="sr-only">Arguments and response of one tool call</DialogDescription>
            </DialogHeader>
            <DialogBody>{selected ? <ToolCallDetail call={selected} total={calls.length} /> : null}</DialogBody>
            {pager}
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}

function FilterChips({
  calls,
  filter,
  onChange,
}: {
  calls: ToolCall[];
  filter: ToolCallFilter;
  onChange: (filter: ToolCallFilter) => void;
}) {
  const failed = calls.filter((call) => call.success === false).length;
  const open = calls.filter((call) => call.success === null).length;
  const chips: { key: string; label: string; count: number; filter: ToolCallFilter }[] = [
    { key: "all", label: "All", count: calls.length, filter: { kind: "all" } },
    ...(failed ? [{ key: "failed", label: "Failed", count: failed, filter: { kind: "failed" } as const }] : []),
    ...(open ? [{ key: "open", label: "No result", count: open, filter: { kind: "open" } as const }] : []),
    ...toolCounts(calls).map(({ toolName, count }) => ({
      key: `tool:${toolName}`,
      label: toolName,
      count,
      filter: { kind: "tool", toolName } as const,
    })),
  ];
  if (calls.length === 0) return null;

  return (
    <div className="run-inspector-chips" role="group" aria-label="Filter tool calls">
      {chips.map((chip) => (
        <Toggle
          key={chip.key}
          pressed={filterKey(filter) === chip.key}
          onPressedChange={() => onChange(chip.filter)}
          className={chip.key === "failed" ? "run-inspector-chip run-inspector-chip--failed" : "run-inspector-chip"}
        >
          {chip.label} <b>{chip.count}</b>
        </Toggle>
      ))}
    </div>
  );
}

function filterKey(filter: ToolCallFilter): string {
  return filter.kind === "tool" ? `tool:${filter.toolName}` : filter.kind;
}

function CallRow({ call, selected, onClick }: { call: ToolCall; selected: boolean; onClick: () => void }) {
  const duration = durationMs(call);
  const summary = argumentSummary(call);

  return (
    <li className="run-inspector-timeline__item">
      <Button
        type="button"
        variant="ghost"
        className="run-inspector-timeline__row"
        aria-current={selected ? "true" : undefined}
        onClick={onClick}
      >
        <span className={`run-inspector-timeline__node run-inspector-timeline__node--${nodeTone(call)}`} aria-hidden="true">
          {call.sequence}
        </span>
        <span className="run-inspector-timeline__text">
          <strong>{toolCallTitle(call)}</strong>
          <code>{call.toolName}</code>
          {summary ? <small>{summary}</small> : null}
        </span>
        <span className="run-inspector-timeline__end">
          {call.success === true ? null : <ToolCallBadge call={call} />}
          {call.startedAt ? <time dateTime={call.startedAt}>{formatClockTime(call.startedAt)}</time> : null}
          {duration !== null ? <span>{formatMs(duration)}</span> : null}
        </span>
      </Button>
    </li>
  );
}

function nodeTone(call: ToolCall): "ok" | "failed" | "open" {
  if (call.success === false) return "failed";
  return call.success === null ? "open" : "ok";
}

function EdgeRow({
  icon,
  title,
  detail,
  onClick,
}: {
  icon: ReactNode;
  title: string;
  detail: string;
  onClick: () => void;
}) {
  return (
    <li className="run-inspector-timeline__item">
      <Button type="button" variant="ghost" className="run-inspector-timeline__row" onClick={onClick}>
        <span className="run-inspector-timeline__node run-inspector-timeline__node--edge" aria-hidden="true">
          {icon}
        </span>
        <span className="run-inspector-timeline__text">
          <strong>{title}</strong>
          <small>{detail}</small>
        </span>
      </Button>
    </li>
  );
}

function Pager({ index, count, onMove }: { index: number; count: number; onMove: (index: number) => void }) {
  return (
    <nav className="run-inspector-pager" aria-label="Walk through tool calls">
      <Button variant="outline" disabled={index <= 0} onClick={() => onMove(index - 1)}>
        <ChevronLeft className="h-4 w-4" />
        Previous
      </Button>
      <span>
        {index + 1} of {count}
      </span>
      <Button variant="outline" disabled={index >= count - 1} onClick={() => onMove(index + 1)}>
        Next
        <ChevronRight className="h-4 w-4" />
      </Button>
    </nav>
  );
}

/** Whether an element is at least `px` wide, following it as it resizes (the page's width, not the window's). */
function useWidthAtLeast(ref: RefObject<HTMLElement | null>, px: number): boolean {
  const [wide, setWide] = useState(false);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWide(entry.contentRect.width >= px));
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref, px]);
  return wide;
}
