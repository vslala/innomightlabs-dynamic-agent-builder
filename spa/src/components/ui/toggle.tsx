import * as React from "react";
import { cn } from "../../lib/utils";

export interface ToggleProps
  extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "onChange"> {
  pressed: boolean;
  onPressedChange?: (pressed: boolean) => void;
}

const Toggle = React.forwardRef<HTMLButtonElement, ToggleProps>(
  ({ className, pressed, onPressedChange, disabled, onClick, children, ...props }, ref) => {
    const handleClick = (event: React.MouseEvent<HTMLButtonElement>) => {
      onClick?.(event);
      if (!event.defaultPrevented) {
        onPressedChange?.(!pressed);
      }
    };

    return (
      <button
        ref={ref}
        type="button"
        role="switch"
        aria-checked={pressed}
        data-state={pressed ? "on" : "off"}
        disabled={disabled}
        onClick={handleClick}
        className={cn(
          "inline-flex shrink-0 items-center gap-2 rounded-full border px-3 py-2 text-sm font-medium leading-none transition-all duration-200",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--gradient-start)]/50",
          "disabled:pointer-events-none disabled:opacity-50",
          pressed
            ? "border-[var(--gradient-start)] bg-[rgba(var(--gradient-start-rgb),0.16)] text-[var(--text-primary)]"
            : "border-[var(--border-subtle)] bg-[var(--surface-control)] text-[var(--text-secondary)] hover:bg-[var(--surface-control-hover)] hover:text-[var(--text-primary)]",
          className
        )}
        {...props}
      >
        {children}
      </button>
    );
  }
);
Toggle.displayName = "Toggle";

export { Toggle };
