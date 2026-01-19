import { cn } from "../../lib/utils";
import { Card, CardContent } from "./card";
import { Button } from "./button";
import type { LucideIcon } from "lucide-react";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
}

function EmptyState({
  icon: Icon,
  title,
  description,
  actionLabel,
  onAction,
  className,
}: EmptyStateProps) {
  return (
    <Card className={className}>
      <CardContent className="p-12">
        <div className="text-center">
          <Icon className="h-16 w-16 mx-auto text-[var(--text-muted)] mb-4" />
          <h3 className="text-lg font-medium text-[var(--text-primary)] mb-2">
            {title}
          </h3>
          <p className="text-[var(--text-muted)] mb-6 max-w-sm mx-auto">
            {description}
          </p>
          {actionLabel && onAction && (
            <Button onClick={onAction}>{actionLabel}</Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

interface InlineEmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  className?: string;
}

function InlineEmptyState({
  icon: Icon,
  title,
  description,
  className,
}: InlineEmptyStateProps) {
  return (
    <div className={cn("text-center py-8", className)}>
      <Icon className="h-12 w-12 mx-auto text-[var(--text-muted)] mb-4 opacity-50" />
      <p className="text-[var(--text-muted)]">{title}</p>
      {description && (
        <p className="text-sm text-[var(--text-muted)] mt-1">{description}</p>
      )}
    </div>
  );
}

export { EmptyState, InlineEmptyState };
