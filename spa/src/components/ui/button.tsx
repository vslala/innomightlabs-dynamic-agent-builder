import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const buttonVariants = cva(
  "inline-flex box-border shrink-0 items-center justify-center whitespace-nowrap rounded-lg text-center text-sm font-medium leading-none transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--gradient-start)]/50 disabled:pointer-events-none disabled:opacity-50 [&>span]:min-w-0 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-gradient-to-r from-[var(--gradient-start)] to-[var(--gradient-mid)] text-white hover:opacity-90 hover:shadow-lg hover:shadow-[var(--gradient-start)]/25",
        destructive:
          "bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20",
        outline:
          "border border-[var(--border-subtle)] bg-transparent hover:bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
        secondary:
          "bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]",
        ghost:
          "hover:bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
        link: "text-[var(--gradient-start)] underline-offset-4 hover:underline",
      },
      size: {
        default: "",
        sm: "rounded-md text-sm",
        action: "rounded-md text-sm",
        lg: "rounded-xl text-base",
        icon: "",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

const buttonSizeStyles: Record<string, React.CSSProperties> = {
  default: {
    minHeight: "var(--control-height-md)",
    paddingInline: "var(--control-padding-x-md)",
    paddingBlock: "var(--space-3)",
  },
  sm: {
    minHeight: "var(--control-height-sm)",
    paddingInline: "var(--control-padding-x-sm)",
    paddingBlock: "var(--space-2)",
  },
  action: {
    minHeight: "var(--control-height-sm)",
    minWidth: "max-content",
    paddingInline: "var(--control-padding-x-md)",
    paddingBlock: "var(--space-2)",
  },
  lg: {
    minHeight: "var(--control-height-lg)",
    paddingInline: "var(--control-padding-x-lg)",
    paddingBlock: "var(--space-3)",
  },
  icon: {
    height: "var(--control-height-sm)",
    width: "var(--control-height-sm)",
    padding: 0,
  },
};

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, style, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    const resolvedSize = size ?? "default";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        style={{
          boxSizing: "border-box",
          gap: "var(--space-2)",
          ...(buttonSizeStyles[resolvedSize] ?? buttonSizeStyles.default),
          ...style,
        }}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
