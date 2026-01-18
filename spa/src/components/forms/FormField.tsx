/**
 * FormField component - renders a form field based on its type.
 */

import { Label } from "../ui/label";
import { Input } from "../ui/input";
import { Textarea } from "../ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import type { FormInput } from "../../types/form";

interface FormFieldProps {
  field: FormInput;
  value: string;
  onChange: (value: string) => void;
}

export function FormField({ field, value, onChange }: FormFieldProps) {
  const renderInput = () => {
    switch (field.input_type) {
      case "text":
        return (
          <Input
            id={field.name}
            name={field.name}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={`Enter ${field.label.toLowerCase()}`}
          />
        );

      case "text_area":
        return (
          <Textarea
            id={field.name}
            name={field.name}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={`Enter ${field.label.toLowerCase()}`}
            rows={4}
          />
        );

      case "password":
        return (
          <Input
            id={field.name}
            name={field.name}
            type="password"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={`Enter ${field.label.toLowerCase()}`}
          />
        );

      case "select":
        // Support both simple values array and options with value/label pairs
        const selectOptions = field.options
          ? field.options.map((opt) => ({ value: opt.value, label: opt.label }))
          : field.values?.map((v) => ({ value: v, label: v })) || [];

        return (
          <Select value={value} onValueChange={onChange}>
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

      case "choice":
        // Support both simple values array and options with value/label pairs
        const choiceOptions = field.options
          ? field.options.map((opt) => ({ value: opt.value, label: opt.label }))
          : field.values?.map((v) => ({ value: v, label: v })) || [];

        return (
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
            {choiceOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => onChange(option.value)}
                style={{
                  padding: "0.5rem 1rem",
                  borderRadius: "0.5rem",
                  border: value === option.value
                    ? "1px solid var(--gradient-start)"
                    : "1px solid var(--border-subtle)",
                  backgroundColor: value === option.value
                    ? "rgba(102, 126, 234, 0.2)"
                    : "rgba(255, 255, 255, 0.05)",
                  color: value === option.value
                    ? "var(--text-primary)"
                    : "var(--text-secondary)",
                  transition: "all 0.2s",
                  cursor: "pointer",
                }}
              >
                {option.label}
              </button>
            ))}
          </div>
        );

      default:
        return (
          <Input
            id={field.name}
            name={field.name}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={`Enter ${field.label.toLowerCase()}`}
          />
        );
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      <Label htmlFor={field.name}>{field.label}</Label>
      {renderInput()}
    </div>
  );
}
