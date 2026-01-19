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

const statusBadgeVariants = cva("inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded font-medium", {
  variants: {
    status: {
      pending: "bg-yellow-500/10 text-yellow-400",
      in_progress: "bg-blue-500/10 text-blue-400",
      completed: "bg-green-500/10 text-green-400",
      failed: "bg-red-500/10 text-red-400",
      cancelled: "bg-gray-500/10 text-gray-400",
      active: "bg-green-500/10 text-green-400",
      inactive: "bg-gray-500/10 text-gray-400",
      success: "bg-green-500/10 text-green-400",
      error: "bg-red-500/10 text-red-400",
      warning: "bg-yellow-500/10 text-yellow-400",
      info: "bg-blue-500/10 text-blue-400",
    },
    size: {
      sm: "text-xs px-1.5 py-0.5",
      default: "text-xs px-2 py-1",
      lg: "text-sm px-2.5 py-1.5",
    },
  },
  defaultVariants: {
    status: "pending",
    size: "default",
  },
});

type StatusType =
  | "pending"
  | "in_progress"
  | "completed"
  | "failed"
  | "cancelled"
  | "active"
  | "inactive"
  | "success"
  | "error"
  | "warning"
  | "info";

export interface StatusBadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof statusBadgeVariants> {
  status: StatusType;
  showIcon?: boolean;
  label?: string;
}

const statusIcons: Record<StatusType, React.ReactNode> = {
  pending: <Clock className="h-3 w-3" />,
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
};

const statusLabels: Record<StatusType, string> = {
  pending: "Pending",
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
      "text-yellow-400": status === "pending" || status === "warning",
      "text-blue-400": status === "in_progress" || status === "info",
      "text-green-400": status === "completed" || status === "active" || status === "success",
      "text-red-400": status === "failed" || status === "error",
      "text-gray-400": status === "cancelled" || status === "inactive",
    },
    className
  );

  switch (status) {
    case "pending":
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
      return <XCircle className={iconClass} />;
  }
}

export { StatusBadge, StatusIcon, statusBadgeVariants };
