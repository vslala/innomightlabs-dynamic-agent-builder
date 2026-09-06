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
import styles from "./status-badge.module.css";

const statusBadgeVariants = cva(styles.badge, {
  variants: {
    status: {
      pending: styles.statusPending,
      draft: styles.statusDraft,
      in_progress: styles.statusInProgress,
      completed: styles.statusCompleted,
      failed: styles.statusFailed,
      cancelled: styles.statusCancelled,
      active: styles.statusActive,
      inactive: styles.statusInactive,
      success: styles.statusSuccess,
      error: styles.statusError,
      warning: styles.statusWarning,
      info: styles.statusInfo,
      no_status: styles.statusNoStatus,
    },
    size: {
      sm: styles.sizeSm,
      default: styles.sizeDefault,
      lg: styles.sizeLg,
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
  pending: <Clock className={styles.statusIconSmall} />,
  draft: <Clock className={styles.statusIconSmall} />,
  in_progress: <Loader2 className={cn(styles.statusIconSmall, styles.iconSpin)} />,
  completed: <CheckCircle className={styles.statusIconSmall} />,
  failed: <AlertCircle className={styles.statusIconSmall} />,
  cancelled: <XCircle className={styles.statusIconSmall} />,
  active: <CheckCircle className={styles.statusIconSmall} />,
  inactive: <XCircle className={styles.statusIconSmall} />,
  success: <CheckCircle className={styles.statusIconSmall} />,
  error: <AlertCircle className={styles.statusIconSmall} />,
  warning: <AlertCircle className={styles.statusIconSmall} />,
  info: <AlertCircle className={styles.statusIconSmall} />,
  no_status: <XCircle className={styles.statusIconSmall} />,
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
    styles.icon,
    {
      [styles.iconWarning]: status === "pending" || status === "draft" || status === "warning",
      [styles.iconInfo]: status === "in_progress" || status === "info",
      [styles.iconSuccess]: status === "completed" || status === "active" || status === "success",
      [styles.iconDanger]: status === "failed" || status === "error",
      [styles.iconMuted]: status === "cancelled" || status === "inactive" || status === "no_status",
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
      return <Loader2 className={cn(iconClass, styles.iconSpin)} />;
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
