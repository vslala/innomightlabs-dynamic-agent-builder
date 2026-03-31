import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../ui/select";
import type { FormInput, FormValue } from "../../../types/form";

interface Props {
  field: FormInput;
  value: FormValue;
  onChange: (value: FormValue) => void;
}

export function SelectField({ field, value, onChange }: Props) {
  // Support both simple values array and options with value/label pairs
  const selectOptions = field.options
    ? field.options.map((opt) => ({ value: opt.value, label: opt.label }))
    : field.values?.map((v) => ({ value: v, label: v })) || [];

  return (
    <Select value={typeof value === "string" ? value : undefined} onValueChange={onChange}>
      <SelectTrigger>
        <SelectValue placeholder={`Select ${field.label.toLowerCase()}`} />
      </SelectTrigger>
      <SelectContent>
        {selectOptions.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
