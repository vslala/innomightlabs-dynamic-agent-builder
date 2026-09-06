import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";
import { AlertCircle, CheckCircle, Info, AlertTriangle, X } from "lucide-react";
import styles from "./alert.module.css";

const alertVariants = cva(styles.alert, {
  variants: {
    variant: {
      default: styles.variantDefault,
      error: styles.variantError,
      warning: styles.variantWarning,
      success: styles.variantSuccess,
      info: styles.variantInfo,
    },
  },
  defaultVariants: {
    variant: "default",
  },
});

const Alert = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof alertVariants>
>(({ className, variant, ...props }, ref) => (
  <div
    ref={ref}
    role="alert"
    className={cn(alertVariants({ variant }), className)}
    {...props}
  />
));
Alert.displayName = "Alert";

const AlertTitle = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
  <h5
    ref={ref}
    className={cn(styles.alertTitle, className)}
    {...props}
  />
));
AlertTitle.displayName = "AlertTitle";

const AlertDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(styles.alertDescription, className)}
    {...props}
  />
));
AlertDescription.displayName = "AlertDescription";

interface AlertBannerProps {
  message: string;
  variant?: "error" | "warning" | "success" | "info";
  onDismiss?: () => void;
  className?: string;
}

function AlertBanner({
  message,
  variant = "error",
  onDismiss,
  className,
}: AlertBannerProps) {
  const icons = {
    error: AlertCircle,
    warning: AlertTriangle,
    success: CheckCircle,
    info: Info,
  };

  const Icon = icons[variant];

  return (
    <div className={cn(alertVariants({ variant }), className)}>
      <div className={styles.bannerRow}>
        <Icon className={styles.bannerIcon} />
        <span className={styles.bannerMessage}>{message}</span>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className={styles.bannerDismiss}
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}

interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
  className?: string;
}

function ErrorState({ message, onRetry, className }: ErrorStateProps) {
  return (
    <div className={cn(styles.errorState, className)}>
      <p className={styles.errorMessage}>{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className={styles.retryButton}
        >
          Try Again
        </button>
      )}
    </div>
  );
}

export { Alert, AlertTitle, AlertDescription, AlertBanner, ErrorState, alertVariants };
