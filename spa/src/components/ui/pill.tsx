import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";
import { X } from "lucide-react";

const pillVariants = cva(
  "inline-flex items-center rounded font-medium transition-colors",
  {
    variants: {
      variant: {
        default:
          "bg-[var(--bg-tertiary)] text-[var(--text-secondary)]",
        primary:
          "bg-[var(--gradient-start)]/10 text-[var(--gradient-start)]",
        secondary:
          "bg-white/5 text-[var(--text-secondary)]",
        outline:
          "border border-[var(--border-subtle)] text-[var(--text-secondary)]",
        success: "bg-green-500/10 text-green-400",
        warning: "bg-yellow-500/10 text-yellow-400",
        error: "bg-red-500/10 text-red-400",
        info: "bg-blue-500/10 text-blue-400",
      },
      size: {
        sm: "px-1.5 py-0.5 text-xs",
        default: "px-2 py-1 text-xs",
        lg: "px-3 py-1.5 text-sm",
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
