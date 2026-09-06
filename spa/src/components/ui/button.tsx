import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";
import styles from "./button.module.css";

const buttonVariants = cva(styles.button, {
  variants: {
    variant: {
      default: styles.variantDefault,
      destructive: styles.variantDestructive,
      outline: styles.variantOutline,
      secondary: styles.variantSecondary,
      ghost: styles.variantGhost,
      link: styles.variantLink,
    },
    size: {
      default: "",
      sm: styles.sizeSm,
      action: styles.sizeAction,
      lg: styles.sizeLg,
      icon: "",
    },
  },
  defaultVariants: {
    variant: "default",
    size: "default",
  },
});

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
    const resolvedVariant = variant ?? "default";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        style={{
          boxSizing: "border-box",
          gap: "var(--space-2)",
          color: resolvedVariant === "default" ? "var(--text-inverse)" : undefined,
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
