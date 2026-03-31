import clsx from "clsx";
import type { FormInput, FormValue } from "../../../types/form";
import styles from "./ChoiceField.module.css";

interface Props {
  field: FormInput;
  value: FormValue;
  onChange: (value: FormValue) => void;
}

export function ChoiceField({ field, value, onChange }: Props) {
  const choiceOptions = field.options
    ? field.options.map((opt) => ({ value: opt.value, label: opt.label }))
    : field.values?.map((v) => ({ value: v, label: v })) || [];

  return (
    <div className={styles.container}>
      {choiceOptions.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          className={clsx(
            styles.choiceButton,
            value === option.value && styles.choiceButtonActive
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
