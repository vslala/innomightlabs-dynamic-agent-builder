/**
 * ViewField component - renders a read-only field based on its type.
 */

import { Label } from "../ui/label";
import type { FormInput } from "../../types/form";

interface ViewFieldProps {
  field: FormInput;
  value: string;
}

export function ViewField({ field, value }: ViewFieldProps) {
  const renderValue = () => {
    // Password fields are hidden in view mode
    if (field.input_type === "password") {
      return null;
    }

    // Select and choice fields render as badges
    if (field.input_type === "select" || field.input_type === "choice") {
      return (
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            padding: "0.375rem 0.75rem",
            borderRadius: "0.375rem",
            fontSize: "0.75rem",
            fontWeight: 500,
            backgroundColor: "rgba(102, 126, 234, 0.1)",
            color: "var(--gradient-start)",
          }}
        >
          {value || "Not set"}
        </span>
      );
    }

    // Text area fields render with pre-wrap
    if (field.input_type === "text_area") {
      return (
        <p
          style={{
            color: "var(--text-secondary)",
            whiteSpace: "pre-wrap",
            lineHeight: "1.6",
          }}
        >
          {value || "Not set"}
        </p>
      );
    }

    // Default text display
    return (
      <p style={{ color: "var(--text-primary)", fontSize: "1rem" }}>
        {value || "Not set"}
      </p>
    );
  };

  // Don't render password fields at all
  if (field.input_type === "password") {
    return null;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      <Label style={{ color: "var(--text-muted)" }}>{field.label}</Label>
      {renderValue()}
    </div>
  );
}
