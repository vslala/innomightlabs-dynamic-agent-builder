import { useEffect, useMemo, useState } from "react";
import { FieldGroup, FormActions, FormStack, Stack } from "../layout";
import {
  Button,
  Checkbox,
  Input,
  Label,
  Radio,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Textarea,
} from "../ui";
import type { FormInput, FormSchema } from "../../types/form";

export type FormAnswer = {
  field_id: string;
  label: string;
  value: string;
};

interface ChatFormRendererProps {
  form: FormSchema;
  submitLabel?: string;
  onSubmit: (answers: FormAnswer[]) => void | Promise<void>;
  onCancel?: () => void;
  disabled?: boolean;
}

function normalizePlaceholder(input: FormInput): string | undefined {
  const placeholder = input.attr?.placeholder;
  return typeof placeholder === "string" ? placeholder : undefined;
}

function getChoiceOptions(input: FormInput): Array<{ value: string; label: string }> {
  if (input.options?.length) {
    return input.options;
  }
  return (input.values || []).map((value) => ({ value, label: value }));
}

function getChoiceVariant(input: FormInput, optionCount: number): "checkbox" | "radio" {
  const variant = input.attr?.variant;
  if (variant === "radio") return "radio";
  if (variant === "checkbox") return "checkbox";
  if (optionCount <= 1) return "checkbox";
  return "radio";
}

export function ChatFormRenderer({
  form,
  submitLabel = "Submit",
  onSubmit,
  onCancel,
  disabled,
}: ChatFormRendererProps) {
  const initial = useMemo(() => {
    const values: Record<string, string> = {};
    for (const input of form.form_inputs) {
      values[input.name] = input.value ?? "";
    }
    return values;
  }, [form]);

  const [values, setValues] = useState<Record<string, string>>(initial);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setValues(initial);
  }, [initial]);

  const isDisabled = Boolean(disabled || submitting);

  const handleChange = (name: string, value: string) => {
    setValues((prev) => ({ ...prev, [name]: value }));
  };

  const toAnswers = (): FormAnswer[] => {
    const answers: FormAnswer[] = [];

    for (const input of form.form_inputs) {
      const value = (values[input.name] ?? "").trim();

      if (input.input_type === "choice") {
        if (value) {
          answers.push({ field_id: input.name, label: input.label, value });
        }
        continue;
      }

      if (!value) continue;
      answers.push({ field_id: input.name, label: input.label, value });
    }

    return answers;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isDisabled) return;

    setSubmitting(true);
    try {
      await onSubmit(toAnswers());
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <FormStack onSubmit={handleSubmit} style={{ width: "100%", gap: "var(--space-3)" }}>
      <div style={{ fontWeight: 700, fontSize: "0.875rem", color: "var(--text-primary)" }}>{form.form_name}</div>

      {form.form_inputs.map((input) => {
        const value = values[input.name] ?? "";

        if (input.input_type === "text_area") {
          return (
            <FieldGroup key={input.name}>
              <Label>{input.label}</Label>
              <Textarea
                value={value}
                placeholder={normalizePlaceholder(input)}
                onChange={(e) => handleChange(input.name, e.target.value)}
                disabled={isDisabled}
                rows={4}
                style={{ resize: "vertical" }}
              />
            </FieldGroup>
          );
        }

        if (input.input_type === "select") {
          const options = input.options?.length
            ? input.options
            : (input.values || []).map((item) => ({ value: item, label: item }));

          return (
            <FieldGroup key={input.name}>
              <Label>{input.label}</Label>
              <Select
                value={value || undefined}
                onValueChange={(nextValue) => handleChange(input.name, nextValue)}
                disabled={isDisabled}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select..." />
                </SelectTrigger>
                <SelectContent>
                {options.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
                </SelectContent>
              </Select>
            </FieldGroup>
          );
        }

        if (input.input_type === "choice") {
          const options = getChoiceOptions(input);
          const variant = getChoiceVariant(input, options.length);

          if (variant === "checkbox" && options.length <= 1) {
            const yesValue = options[0]?.value || "yes";
            const checked = value === yesValue;

            return (
              <label key={input.name} style={{ display: "flex", alignItems: "center", gap: "0.625rem", fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                <Checkbox
                  checked={checked}
                  onChange={(e) => handleChange(input.name, e.target.checked ? yesValue : "")}
                  disabled={isDisabled}
                />
                <span>{input.label}</span>
              </label>
            );
          }

          if (variant === "checkbox") {
            const selected = new Set(
              value
                .split(",")
                .map((item) => item.trim())
                .filter(Boolean)
            );

            return (
              <fieldset key={input.name} disabled={isDisabled} style={{ margin: 0, padding: 0, border: 0 }}>
                <legend style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>{input.label}</legend>
                <Stack gap="xs">
                {options.map((option) => (
                  <label key={option.value} style={{ display: "flex", alignItems: "center", gap: "0.625rem", fontSize: "0.8125rem", color: "var(--text-primary)" }}>
                    <Checkbox
                      checked={selected.has(option.value)}
                      onChange={(e) => {
                        const next = new Set(selected);
                        if (e.target.checked) {
                          next.add(option.value);
                        } else {
                          next.delete(option.value);
                        }
                        handleChange(input.name, Array.from(next).join(", "));
                      }}
                      disabled={isDisabled}
                    />
                    <span>{option.label}</span>
                  </label>
                ))}
                </Stack>
              </fieldset>
            );
          }

          return (
            <fieldset key={input.name} disabled={isDisabled} style={{ margin: 0, padding: 0, border: 0 }}>
              <legend style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>{input.label}</legend>
              <Stack gap="xs">
              {options.map((option) => (
                <label key={option.value} style={{ display: "flex", alignItems: "center", gap: "0.625rem", fontSize: "0.8125rem", color: "var(--text-primary)" }}>
                  <Radio
                    name={input.name}
                    value={option.value}
                    checked={value === option.value}
                    onChange={(e) => handleChange(input.name, e.target.value)}
                    disabled={isDisabled}
                  />
                  <span>{option.label}</span>
                </label>
              ))}
              </Stack>
            </fieldset>
          );
        }

        return (
          <FieldGroup key={input.name}>
            <Label>{input.label}</Label>
            <Input
              type="text"
              value={value}
              placeholder={normalizePlaceholder(input)}
              onChange={(e) => handleChange(input.name, e.target.value)}
              disabled={isDisabled}
            />
          </FieldGroup>
        );
      })}

      <FormActions align="end" style={{ paddingTop: "var(--space-1)" }}>
        {onCancel && (
          <Button
            type="button"
            variant="outline"
            onClick={onCancel}
            disabled={isDisabled}
          >
            Cancel
          </Button>
        )}
        <Button
          type="submit"
          disabled={isDisabled}
        >
          {submitLabel}
        </Button>
      </FormActions>
    </FormStack>
  );
}
