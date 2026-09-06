import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";
import { X } from "lucide-react";
import styles from "./pill.module.css";

const pillVariants = cva(styles.pill, {
  variants: {
    variant: {
      default: styles.variantDefault,
      primary: styles.variantPrimary,
      secondary: styles.variantSecondary,
      outline: styles.variantOutline,
      success: styles.variantSuccess,
      warning: styles.variantWarning,
      error: styles.variantError,
      info: styles.variantInfo,
    },
    size: {
      sm: styles.sizeSm,
      default: styles.sizeDefault,
      lg: styles.sizeLg,
    },
  },
  defaultVariants: {
    variant: "default",
    size: "default",
  },
});

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
          className={styles.removeButton}
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
    <div className={cn(styles.group, className)}>{children}</div>
  );
}

export { Pill, PillGroup, pillVariants };
