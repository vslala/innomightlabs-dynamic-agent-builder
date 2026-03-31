import { Textarea } from "../../ui/textarea";
import { MarkdownRenderer } from "../../ui/markdown-renderer";
import type { FormInput, FormValue } from "../../../types/form";
import styles from "./TextAreaField.module.css";

interface Props {
  field: FormInput;
  value: FormValue;
  onChange: (value: FormValue) => void;
}

export function TextAreaField({ field, value, onChange }: Props) {
  const fieldAttributes = field.attr || {};
  const placeholderText = fieldAttributes.placeholder || `Enter ${field.label.toLowerCase()}`;
  const textAreaValue = typeof value === "string" ? value : "";

  return (
    <div className={styles.wrapper}>
      <Textarea
        id={field.name}
        name={field.name}
        value={textAreaValue}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholderText}
        rows={fieldAttributes.rows ? parseInt(fieldAttributes.rows, 10) : 4}
        className="min-h-[140px] bg-white/6 text-base leading-7"
      />

      <div className={styles.previewCard}>
        <div className={styles.previewHeader}>
          <span className={styles.previewTitle}>Preview</span>
          <span className={styles.previewSubtitle}>Markdown rendered live</span>
        </div>

        <div className={styles.previewBody}>
          {textAreaValue.trim() ? (
            <MarkdownRenderer content={textAreaValue} />
          ) : (
            <p className={styles.previewPlaceholder}>Start typing to preview formatted markdown.</p>
          )}
        </div>
      </div>
    </div>
  );
}
