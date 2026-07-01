import type { FormInput, FormValue } from "../../../types/form";
import { Button } from "../../ui/button";
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
        <Button
          key={option.value}
          type="button"
          variant={value === option.value ? "default" : "outline"}
          size="sm"
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </Button>
      ))}
    </div>
  );
}
