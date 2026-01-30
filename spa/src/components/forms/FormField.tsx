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
import type { FormInput, FormValue } from "../../types/form";
import { AttachmentChip } from "../chat/AttachmentChip";

interface FormFieldProps {
  field: FormInput;
  value: FormValue;
  onChange: (value: FormValue) => void;
}

export function FormField({ field, value, onChange }: FormFieldProps) {
  const fieldAttributes = field.attr || {};
  const placeholderText = fieldAttributes.placeholder || `Enter ${field.label.toLowerCase()}`;

  const renderFileList = () => {
    const files = value instanceof FileList
      ? Array.from(value)
      : Array.isArray(value)
        ? value
        : [];

    if (files.length === 0) return null;

    return (
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
        {files.map((file) => (
          <AttachmentChip
            key={`${file.name}-${file.size}-${file.lastModified}`}
            filename={file.name}
            size={file.size}
            readonly
          />
        ))}
      </div>
    );
  };

  const renderInput = () => {
    switch (field.input_type) {
      case "text":
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

      case "text_area":
        return (
          <Textarea
            id={field.name}
            name={field.name}
            value={typeof value === "string" ? value : ""}
            onChange={(e) => onChange(e.target.value)}
            placeholder={placeholderText}
            rows={fieldAttributes.rows ? parseInt(fieldAttributes.rows, 10) : 4}
          />
        );

      case "password":
        return (
          <Input
            id={field.name}
            name={field.name}
            type="password"
            value={typeof value === "string" ? value : ""}
            onChange={(e) => onChange(e.target.value)}
            placeholder={placeholderText}
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

      case "file_upload":
        return (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <Input
              id={field.name}
              name={field.name}
              type="file"
              accept={fieldAttributes.accept}
              multiple={fieldAttributes.multiple === "true"}
              onChange={(e) => onChange(e.target.files)}
            />
            {renderFileList()}
          </div>
        );

      default:
        return (
          <Input
            id={field.name}
            name={field.name}
            value={typeof value === "string" ? value : ""}
            onChange={(e) => onChange(e.target.value)}
            placeholder={placeholderText}
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
