import * as React from "react";
import { cn } from "../../lib/utils";
import styles from "./switch.module.css";

export interface SwitchProps
  extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "onChange"> {
  checked: boolean;
  onCheckedChange?: (checked: boolean) => void;
}

/** An on/off setting that applies at once, drawn as a track with a sliding knob. Label it with a wrapping `<label>` or `aria-label`. */
const Switch = React.forwardRef<HTMLButtonElement, SwitchProps>(
  ({ className, checked, onCheckedChange, onClick, ...props }, ref) => (
    <button
      ref={ref}
      type="button"
      role="switch"
      aria-checked={checked}
      data-state={checked ? "on" : "off"}
      onClick={(event) => {
        onClick?.(event);
        if (!event.defaultPrevented) onCheckedChange?.(!checked);
      }}
      className={cn(styles.track, checked ? styles.on : styles.off, className)}
      {...props}
    >
      <span className={styles.knob} />
    </button>
  )
);
Switch.displayName = "Switch";

export { Switch };
