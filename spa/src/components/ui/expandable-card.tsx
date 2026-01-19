import * as React from "react";
import { cn } from "../../lib/utils";
import { ChevronDown, ChevronRight } from "lucide-react";

interface ExpandableCardProps {
  expanded: boolean;
  onToggle: () => void;
  header: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  headerClassName?: string;
  contentClassName?: string;
}

function ExpandableCard({
  expanded,
  onToggle,
  header,
  children,
  className,
  headerClassName,
  contentClassName,
}: ExpandableCardProps) {
  return (
    <div
      className={cn(
        "border border-[var(--border-subtle)] rounded-lg overflow-hidden",
        className
      )}
    >
      <div
        className={cn(
          "flex items-center p-4 cursor-pointer hover:bg-white/5 transition-colors",
          headerClassName
        )}
        onClick={onToggle}
      >
        <span className="mr-2 text-[var(--text-muted)]">
          {expanded ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
        </span>
        <div className="flex-1">{header}</div>
      </div>

      {expanded && (
        <div
          className={cn(
            "border-t border-[var(--border-subtle)] p-4 bg-[var(--bg-secondary)]",
            contentClassName
          )}
        >
          {children}
        </div>
      )}
    </div>
  );
}

interface CollapsibleSectionProps {
  title: string;
  defaultExpanded?: boolean;
  children: React.ReactNode;
  className?: string;
  headerClassName?: string;
  icon?: React.ReactNode;
}

function CollapsibleSection({
  title,
  defaultExpanded = false,
  children,
  className,
  headerClassName,
  icon,
}: CollapsibleSectionProps) {
  const [expanded, setExpanded] = React.useState(defaultExpanded);

  return (
    <div className={cn("border-t border-[var(--border-subtle)] pt-4", className)}>
      <button
        type="button"
        className={cn(
          "flex items-center gap-2 text-xs text-[var(--text-muted)] mb-2 hover:text-[var(--text-secondary)] transition-colors",
          headerClassName
        )}
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? (
          <ChevronDown className="h-3 w-3" />
        ) : (
          <ChevronRight className="h-3 w-3" />
        )}
        {icon}
        {title}
      </button>
      {expanded && <div>{children}</div>}
    </div>
  );
}

export { ExpandableCard, CollapsibleSection };
