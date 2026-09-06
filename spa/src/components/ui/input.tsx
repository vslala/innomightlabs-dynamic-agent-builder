import * as React from "react";
import { cn } from "../../lib/utils";
import styles from "./input.module.css";

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, type, autoComplete, style, ...props }, ref) => {
    return (
      <input
        type={type}
        autoComplete={autoComplete ?? "off"}
        className={cn(
          styles.input,
          className
        )}
        style={{
          minHeight: "var(--control-height-md)",
          paddingInline: "var(--control-padding-x-sm)",
          paddingBlock: "var(--space-3)",
          boxSizing: "border-box",
          ...style,
        }}
        ref={ref}
        {...props}
      />
    );
  }
);
Input.displayName = "Input";

export { Input };
