import { useState, type FormEvent } from "react";

import type { FormInput } from "../api";
import { choiceOptions, choiceVariant, collectAnswers, formatSubmission } from "../forms";
import type { PendingForm } from "../useChat";

interface FormCardProps {
  pending: PendingForm;
  disabled: boolean;
  onSubmit: (content: string, display: string) => void;
}

export function FormCard({ pending, disabled, onSubmit }: FormCardProps) {
  const { form, submitLabel } = pending;
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(form.form_inputs.map((input) => [input.name, input.value ?? ""]))
  );

  const setValue = (name: string, value: string) => setValues((prev) => ({ ...prev, [name]: value }));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const answers = collectAnswers(form, values);
    onSubmit(formatSubmission(form, answers), `Submitted: ${form.form_name}`);
  };

  return (
    <form className="ie-form" onSubmit={submit}>
      <div className="ie-form-title">{form.form_name}</div>
      <fieldset className="ie-form-fields" disabled={disabled}>
        {form.form_inputs.map((input) => (
          <Field key={input.name} input={input} value={values[input.name] ?? ""} onChange={(value) => setValue(input.name, value)} />
        ))}
      </fieldset>
      <button type="submit" className="ie-button ie-button-primary" disabled={disabled}>
        {submitLabel}
      </button>
    </form>
  );
}

interface FieldProps {
  input: FormInput;
  value: string;
  onChange: (value: string) => void;
}

function Field({ input, value, onChange }: FieldProps) {
  const placeholder = input.attr?.placeholder;

  if (input.input_type === "file_upload") {
    return <p className="ie-form-note">{input.label}: file uploads aren't supported in this chat.</p>;
  }

  if (input.input_type === "text_area") {
    return (
      <label className="ie-field">
        <span className="ie-field-label">{input.label}</span>
        <textarea className="ie-input" rows={3} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
      </label>
    );
  }

  if (input.input_type === "select") {
    return (
      <label className="ie-field">
        <span className="ie-field-label">{input.label}</span>
        <select className="ie-input" value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">Select…</option>
          {choiceOptions(input).map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
    );
  }

  if (input.input_type === "choice") {
    const options = choiceOptions(input);
    const variant = choiceVariant(input);

    if (variant === "single-checkbox") {
      const yes = options[0]?.value || "yes";
      return (
        <label className="ie-check">
          <input type="checkbox" checked={value === yes} onChange={(e) => onChange(e.target.checked ? yes : "")} />
          <span>{input.label}</span>
        </label>
      );
    }

    const selected = new Set(value.split(",").map((item) => item.trim()).filter(Boolean));
    return (
      <fieldset className="ie-choice-group">
        <legend className="ie-field-label">{input.label}</legend>
        {options.map((option) => (
          <label className="ie-check" key={option.value}>
            {variant === "checkboxes" ? (
              <input
                type="checkbox"
                checked={selected.has(option.value)}
                onChange={(e) => {
                  const next = new Set(selected);
                  if (e.target.checked) next.add(option.value);
                  else next.delete(option.value);
                  onChange(Array.from(next).join(", "));
                }}
              />
            ) : (
              <input type="radio" name={input.name} checked={value === option.value} onChange={() => onChange(option.value)} />
            )}
            <span>{option.label}</span>
          </label>
        ))}
      </fieldset>
    );
  }

  return (
    <label className="ie-field">
      <span className="ie-field-label">{input.label}</span>
      <input
        className="ie-input"
        type={input.input_type === "password" ? "password" : "text"}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}
