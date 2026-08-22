import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";
import { X } from "lucide-react";

const pillVariants = cva(
  "inline-flex min-h-6 items-center justify-center whitespace-nowrap rounded-full font-semibold leading-[1.15] tracking-normal transition-colors",
  {
    variants: {
      variant: {
        default:
          "bg-[var(--surface-subtle)] text-[var(--text-muted)]",
        primary:
          "bg-[var(--accent-blue-bg)] text-[var(--link-color)]",
        secondary:
          "bg-[var(--surface-subtle)] text-[var(--text-secondary)]",
        outline:
          "border border-[var(--border-default)] bg-transparent text-[var(--text-secondary)]",
        success: "bg-[var(--success-bg)] text-[var(--success)]",
        warning: "bg-[var(--warning-bg)] text-[var(--warning)]",
        error: "bg-[var(--danger-bg)] text-[var(--danger)]",
        info: "bg-[var(--accent-blue-bg)] text-[var(--link-color)]",
      },
      size: {
        sm: "min-h-5 px-2.5 py-0.5 text-xs",
        default: "min-h-6 px-2.5 py-1 text-xs",
        lg: "min-h-7 px-3.5 py-1.5 text-base",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface PillProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof pillVariants> {
  onRemove?: () => void;
}

const Pill = React.forwardRef<HTMLSpanElement, PillProps>(
  ({ className, variant, size, children, onRemove, ...props }, ref) => (
    <span
      ref={ref}
      className={cn(pillVariants({ variant, size, className }))}
      {...props}
    >
      {children}
      {onRemove && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className="ml-1 hover:opacity-70 transition-opacity"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </span>
  )
);
Pill.displayName = "Pill";

interface PillGroupProps {
  children: React.ReactNode;
  className?: string;
}

function PillGroup({ children, className }: PillGroupProps) {
  return (
    <div className={cn("flex gap-2 flex-wrap", className)}>{children}</div>
  );
}

export { Pill, PillGroup, pillVariants };
