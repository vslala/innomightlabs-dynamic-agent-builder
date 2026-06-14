import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./select";

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
      <SelectTrigger className="h-10 w-auto max-w-[13rem] shrink-0 rounded-full border-transparent bg-white/8 px-3 text-sm hover:bg-white/12">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            <span className="flex min-w-0 flex-col">
              <span className="truncate">{option.label}</span>
              {option.description && (
                <span className="truncate text-xs text-[var(--text-muted)]">{option.description}</span>
              )}
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

