/**
 * FormField component - renders a form field based on its type.
 *
 * This is intentionally a lightweight dispatcher.
 * Each input_type implementation lives in its own component under ./fields.
 */

import type { FormInput, FormValue } from "../../types/form";
import { FormFieldShell } from "./FormFieldShell";
import { SmartSuggestionControl } from "./SmartSuggestionControl";
import {
  ChoiceField,
  DefaultField,
  FileUploadField,
  KeyValueField,
  PasswordField,
  SelectField,
  TextAreaField,
  TextField,
} from "./fields";

interface FormFieldProps {
  field: FormInput;
  value: FormValue;
  formData: Record<string, FormValue>;
  onChange: (value: FormValue) => void;
}

export function FormField({ field, value, formData, onChange }: FormFieldProps) {
  const renderInput = () => {
    switch (field.input_type) {
      case "text":
        return <TextField field={field} value={value} onChange={onChange} />;

      case "text_area":
        return <TextAreaField field={field} value={value} onChange={onChange} />;

      case "password":
        return <PasswordField field={field} value={value} onChange={onChange} />;

      case "select":
        return <SelectField field={field} value={value} onChange={onChange} />;

      case "choice":
        return <ChoiceField field={field} value={value} onChange={onChange} />;

      case "file_upload":
        return <FileUploadField field={field} value={value} onChange={onChange} />;

      case "key_value":
        return <KeyValueField field={field} value={value} onChange={onChange} />;

      default:
        return <DefaultField field={field} value={value} onChange={onChange} />;
    }
  };

  return (
    <FormFieldShell field={field}>
      {renderInput()}
      {(field.input_type === "text" || field.input_type === "text_area") && field.smart_suggestion && (
        <SmartSuggestionControl
          field={field}
          value={value}
          formData={formData}
          onApply={onChange}
        />
      )}
    </FormFieldShell>
  );
}
