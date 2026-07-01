import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const buttonVariants = cva(
  "inline-flex box-border shrink-0 items-center justify-center gap-2.5 whitespace-nowrap rounded-lg text-center text-sm font-medium leading-none transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 [&>span]:min-w-0 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
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
        default: "min-h-11 px-6 py-2.5",
        sm: "min-h-10 rounded-md px-5 py-2.5 text-sm",
        action: "min-h-10 min-w-40 rounded-md px-6 py-2.5 text-sm",
        lg: "min-h-12 rounded-xl px-8 py-3 text-base",
        icon: "h-10 w-10",
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
    minHeight: "2.75rem",
    paddingInline: "1.5rem",
    paddingBlock: "0.625rem",
  },
  sm: {
    minHeight: "2.5rem",
    paddingInline: "1.25rem",
    paddingBlock: "0.625rem",
  },
  action: {
    minHeight: "2.5rem",
    minWidth: "10rem",
    paddingInline: "1.5rem",
    paddingBlock: "0.625rem",
  },
  lg: {
    minHeight: "3rem",
    paddingInline: "2rem",
    paddingBlock: "0.75rem",
  },
  icon: {
    height: "2.5rem",
    width: "2.5rem",
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
