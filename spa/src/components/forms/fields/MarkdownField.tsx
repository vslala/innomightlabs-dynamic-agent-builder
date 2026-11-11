import { MarkdownEditor } from "../../ui";
import type { FormInput, FormValue } from "../../../types/form";

interface Props {
  field: FormInput;
  value: FormValue;
  onChange: (value: FormValue) => void;
}

/** A `markdown` field: written and read in one place, saved exactly as typed. */
export function MarkdownField({ field, value, onChange }: Props) {
  const attributes = field.attr || {};
  return (
    <MarkdownEditor
      id={field.name}
      value={typeof value === "string" ? value : ""}
      onChange={onChange}
      placeholder={attributes.placeholder || `Write ${field.label.toLowerCase()} in Markdown`}
      minRows={attributes.rows ? parseInt(attributes.rows, 10) : 8}
    />
  );
}
