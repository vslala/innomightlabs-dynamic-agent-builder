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
        return (
          <Select value={value} onValueChange={onChange}>
            <SelectTrigger>
              <SelectValue placeholder={`Select ${field.label.toLowerCase()}`} />
            </SelectTrigger>
            <SelectContent>
              {field.values?.map((option) => (
                <SelectItem key={option} value={option}>
                  {option}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        );

      case "choice":
        return (
          <div className="flex flex-wrap gap-2">
            {field.values?.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => onChange(option)}
                className={`px-4 py-2 rounded-lg border transition-all duration-200 ${
                  value === option
                    ? "border-[var(--gradient-start)] bg-[var(--gradient-start)]/20 text-[var(--text-primary)]"
                    : "border-[var(--border-subtle)] bg-white/5 text-[var(--text-secondary)] hover:bg-white/10"
                }`}
              >
                {option}
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
    <div className="space-y-2">
      <Label htmlFor={field.name}>{field.label}</Label>
      {renderInput()}
    </div>
  );
}
