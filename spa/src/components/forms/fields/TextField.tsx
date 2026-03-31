import { Input } from "../../ui/input";
import type { FormInput, FormValue } from "../../../types/form";

interface Props {
  field: FormInput;
  value: FormValue;
  onChange: (value: FormValue) => void;
}

export function TextField({ field, value, onChange }: Props) {
  const fieldAttributes = field.attr || {};
  const placeholderText = fieldAttributes.placeholder || `Enter ${field.label.toLowerCase()}`;

  return (
    <Input
      id={field.name}
      name={field.name}
      value={typeof value === "string" ? value : ""}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholderText}
      type={fieldAttributes.type || "text"}
      min={fieldAttributes.min}
      max={fieldAttributes.max}
    />
  );
}
