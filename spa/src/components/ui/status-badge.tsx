import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";
import {
  CheckCircle,
  AlertCircle,
  XCircle,
  Loader2,
  Clock,
} from "lucide-react";

const statusBadgeVariants = cva(
  "inline-flex min-h-[1.625rem] items-center justify-center gap-1.5 whitespace-nowrap rounded-full border border-transparent px-3 py-1 text-sm font-semibold leading-[1.15] tracking-normal",
  {
  variants: {
    status: {
      pending: "bg-[var(--warning-bg)] text-[var(--warning)]",
      draft: "bg-[var(--warning-bg)] text-[var(--warning)]",
      in_progress: "bg-[var(--accent-blue-bg)] text-[var(--link-color)]",
      completed: "bg-[var(--success-bg)] text-[var(--success)]",
      failed: "bg-[var(--danger-bg)] text-[var(--danger)]",
      cancelled: "bg-[var(--surface-subtle)] text-[var(--text-muted)]",
      active: "bg-[var(--success-bg)] text-[var(--success)]",
      inactive: "bg-[var(--surface-subtle)] text-[var(--text-muted)]",
      success: "bg-[var(--success-bg)] text-[var(--success)]",
      error: "bg-[var(--danger-bg)] text-[var(--danger)]",
      warning: "bg-[var(--warning-bg)] text-[var(--warning)]",
      info: "bg-[var(--accent-blue-bg)] text-[var(--link-color)]",
      no_status: "bg-[var(--surface-subtle)] text-[var(--text-muted)]",
    },
    size: {
      sm: "min-h-5 px-2.5 py-0.5 text-xs",
      default: "min-h-[1.625rem] px-3 py-1 text-sm",
      lg: "min-h-7 px-3.5 py-1.5 text-base",
    },
  },
  defaultVariants: {
    status: "pending",
    size: "default",
  },
});

type StatusType =
  | "pending"
  | "draft"
  | "in_progress"
  | "completed"
  | "failed"
  | "cancelled"
  | "active"
  | "inactive"
  | "success"
  | "error"
  | "warning"
  | "info"
  | "no_status";

export interface StatusBadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof statusBadgeVariants> {
  status: StatusType;
  showIcon?: boolean;
  label?: string;
}

const statusIcons: Record<StatusType, React.ReactNode> = {
  pending: <Clock className="h-3 w-3" />,
  draft: <Clock className="h-3 w-3" />,
  in_progress: <Loader2 className="h-3 w-3 animate-spin" />,
  completed: <CheckCircle className="h-3 w-3" />,
  failed: <AlertCircle className="h-3 w-3" />,
  cancelled: <XCircle className="h-3 w-3" />,
  active: <CheckCircle className="h-3 w-3" />,
  inactive: <XCircle className="h-3 w-3" />,
  success: <CheckCircle className="h-3 w-3" />,
  error: <AlertCircle className="h-3 w-3" />,
  warning: <AlertCircle className="h-3 w-3" />,
  info: <AlertCircle className="h-3 w-3" />,
  no_status: <XCircle className="h-3 w-3" />,
};

const statusLabels: Record<StatusType, string> = {
  pending: "Pending",
  draft: "Draft",
  in_progress: "In Progress",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
  active: "Active",
  inactive: "Inactive",
  success: "Success",
  error: "Error",
  warning: "Warning",
  info: "Info",
  no_status: "No Status",
};

const StatusBadge = React.forwardRef<HTMLSpanElement, StatusBadgeProps>(
  ({ className, status, size, showIcon = false, label, ...props }, ref) => {
    return (
      <span
        ref={ref}
        className={cn(statusBadgeVariants({ status, size, className }))}
        {...props}
      >
        {showIcon && statusIcons[status]}
        {label ?? statusLabels[status]}
      </span>
    );
  }
);
StatusBadge.displayName = "StatusBadge";

interface StatusIconProps {
  status: StatusType;
  className?: string;
}

function StatusIcon({ status, className }: StatusIconProps) {
  const iconClass = cn(
    "h-4 w-4",
    {
      "text-[var(--warning)]": status === "pending" || status === "draft" || status === "warning",
      "text-[var(--link-color)]": status === "in_progress" || status === "info",
      "text-[var(--success)]": status === "completed" || status === "active" || status === "success",
      "text-[var(--danger)]": status === "failed" || status === "error",
      "text-[var(--text-muted)]": status === "cancelled" || status === "inactive" || status === "no_status",
    },
    className
  );

  switch (status) {
    case "pending":
    case "draft":
    case "warning":
      return <Clock className={iconClass} />;
    case "in_progress":
    case "info":
      return <Loader2 className={cn(iconClass, "animate-spin")} />;
    case "completed":
    case "active":
    case "success":
      return <CheckCircle className={iconClass} />;
    case "failed":
    case "error":
      return <AlertCircle className={iconClass} />;
    case "cancelled":
    case "inactive":
    case "no_status":
      return <XCircle className={iconClass} />;
  }
}

export { StatusBadge, StatusIcon, statusBadgeVariants };
