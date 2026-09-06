import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./select";
import styles from "./pill-select.module.css";

export interface PillSelectOption {
  value: string;
  label: string;
  description?: string;
}

interface PillSelectProps {
  value: string;
  options: PillSelectOption[];
  placeholder?: string;
  onChange: (value: string) => void;
}

export function PillSelect({ value, options, placeholder = "Select", onChange }: PillSelectProps) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className={styles.trigger}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            <span className={styles.optionLabelWrap}>
              <span className={styles.optionLabel}>{option.label}</span>
              {option.description && (
                <span className={styles.optionDescription}>{option.description}</span>
              )}
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

