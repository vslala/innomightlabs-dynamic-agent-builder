import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const spinnerVariants = cva(
  "animate-spin rounded-full border-2 border-[var(--gradient-start)] border-t-transparent",
  {
    variants: {
      size: {
        sm: "h-4 w-4",
        default: "h-6 w-6",
        lg: "h-8 w-8",
        xl: "h-12 w-12",
      },
    },
    defaultVariants: {
      size: "default",
    },
  }
);

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
    <div className={cn("flex items-center justify-center h-64", className)}>
      <Spinner size={size} />
    </div>
  );
}

export { Spinner, LoadingState, spinnerVariants };
