import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";
import styles from "./spinner.module.css";

const spinnerVariants = cva(styles.spinner, {
  variants: {
    size: {
      sm: styles.sizeSm,
      default: styles.sizeDefault,
      lg: styles.sizeLg,
      xl: styles.sizeXl,
    },
  },
  defaultVariants: {
    size: "default",
  },
});

export interface SpinnerProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof spinnerVariants> {}

const Spinner = React.forwardRef<HTMLDivElement, SpinnerProps>(
  ({ className, size, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(spinnerVariants({ size, className }))}
      {...props}
    />
  )
);
Spinner.displayName = "Spinner";

interface LoadingStateProps {
  className?: string;
  size?: "sm" | "default" | "lg" | "xl";
}

function LoadingState({ className, size = "lg" }: LoadingStateProps) {
  return (
    <div className={cn(styles.loadingState, className)}>
      <Spinner size={size} />
    </div>
  );
}

export { Spinner, LoadingState, spinnerVariants };
