import * as React from "react";
import { cn } from "../../lib/utils";
import styles from "./textarea.module.css";

const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.ComponentProps<"textarea">
>(({ className, autoComplete, style, ...props }, ref) => {
  return (
    <textarea
      autoComplete={autoComplete ?? "off"}
      className={cn(styles.textarea, className)}
      style={{
        paddingInline: "var(--control-padding-x-sm)",
        paddingBlock: "var(--space-3)",
        boxSizing: "border-box",
        ...style,
      }}
      ref={ref}
      {...props}
    />
  );
});
Textarea.displayName = "Textarea";

export { Textarea };
