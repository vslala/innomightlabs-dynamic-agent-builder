/** @jsxImportSource preact */
import { useMemo, useState } from 'preact/hooks';
import { Form, FormInput, FormInputType } from '../types';

export type FormAnswer = { field_id: string; label: string; value: string };

interface FormRendererProps {
  form: Form;
  submitLabel?: string;
  onSubmit: (answers: FormAnswer[]) => void | Promise<void>;
  onCancel?: () => void;
  disabled?: boolean;
}

function normalizePlaceholder(input: FormInput): string | undefined {
  const placeholder = input.attr?.placeholder;
  return typeof placeholder === 'string' ? placeholder : undefined;
}

export function FormRenderer({ form, submitLabel = 'Submit', onSubmit, onCancel, disabled }: FormRendererProps) {
  const initial = useMemo(() => {
    const values: Record<string, string> = {};
    for (const input of form.form_inputs) {
      values[input.name] = input.value ?? '';
    }
    return values;
  }, [form]);

  const [values, setValues] = useState<Record<string, string>>(initial);
  const [submitting, setSubmitting] = useState(false);

  const isDisabled = Boolean(disabled || submitting);

  const handleChange = (name: string, value: string) => {
    setValues((prev) => ({ ...prev, [name]: value }));
  };

  const toAnswers = (): FormAnswer[] => {
    const answers: FormAnswer[] = [];
    for (const input of form.form_inputs) {
      const v = (values[input.name] ?? '').trim();

      // For CHOICE, treat non-empty as yes.
      if (input.input_type === 'choice') {
        if (v) {
          answers.push({ field_id: input.name, label: input.label, value: v });
        }
        continue;
      }

      if (!v) continue;
      answers.push({ field_id: input.name, label: input.label, value: v });
    }
    return answers;
  };

  const submit = async (e?: Event) => {
    e?.preventDefault();
    if (isDisabled) return;

    setSubmitting(true);
    try {
      await onSubmit(toAnswers());
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="innomight-form" onSubmit={submit}>
      <div className="innomight-form-title">{form.form_name}</div>

      {form.form_inputs.map((input) => {
        const value = values[input.name] ?? '';

        if (input.input_type === 'text_area') {
          return (
            <label className="innomight-form-field" key={input.name}>
              <span className="innomight-form-label">{input.label}</span>
              <textarea
                className="innomight-form-textarea"
                value={value}
                placeholder={normalizePlaceholder(input)}
                onInput={(e) => handleChange(input.name, (e.target as HTMLTextAreaElement).value)}
                disabled={isDisabled}
                rows={4}
              />
            </label>
          );
        }

        if (input.input_type === 'select') {
          const options = input.options?.length
            ? input.options
            : (input.values || []).map((v) => ({ value: v, label: v }));

          return (
            <label className="innomight-form-field" key={input.name}>
              <span className="innomight-form-label">{input.label}</span>
              <select
                className="innomight-form-select"
                value={value}
                onChange={(e) => handleChange(input.name, (e.target as HTMLSelectElement).value)}
                disabled={isDisabled}
              >
                <option value="">Select…</option>
                {options.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </label>
          );
        }

        if (input.input_type === 'choice') {
          // For now, support a single yes/consent checkbox.
          const checked = Boolean(value);
          const yesValue = (input.values && input.values[0]) || 'yes';
          return (
            <label className="innomight-form-checkbox" key={input.name}>
              <input
                type="checkbox"
                checked={checked}
                onChange={(e) => handleChange(input.name, (e.target as HTMLInputElement).checked ? yesValue : '')}
                disabled={isDisabled}
              />
              <span>{input.label}</span>
            </label>
          );
        }

        // default to text
        return (
          <label className="innomight-form-field" key={input.name}>
            <span className="innomight-form-label">{input.label}</span>
            <input
              type="text"
              className="innomight-form-input"
              value={value}
              placeholder={normalizePlaceholder(input)}
              onInput={(e) => handleChange(input.name, (e.target as HTMLInputElement).value)}
              disabled={isDisabled}
            />
          </label>
        );
      })}

      <div className="innomight-form-actions">
        {onCancel && (
          <button type="button" className="innomight-form-cancel" onClick={onCancel} disabled={isDisabled}>
            Cancel
          </button>
        )}
        <button type="submit" className="innomight-form-submit" disabled={isDisabled}>
          {submitLabel}
        </button>
      </div>
    </form>
  );
}
