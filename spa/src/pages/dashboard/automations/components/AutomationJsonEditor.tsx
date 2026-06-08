import { Button, JsonTreeViewer, Label, Textarea } from "../../../../components/ui";

export function AutomationJsonEditor({
  label,
  value,
  error,
  readOnly = false,
  minHeight = "10rem",
  onChange,
  onFormat,
}: {
  label: string;
  value: string;
  error?: string | null;
  readOnly?: boolean;
  minHeight?: string;
  onChange?: (value: string) => void;
  onFormat?: () => void;
}) {
  return (
    <div className="automation-json-editor">
      <div className="automation-json-editor__header">
        <Label>{label}</Label>
        {onFormat && (
          <Button variant="ghost" size="sm" onClick={onFormat} disabled={readOnly}>
            Format
          </Button>
        )}
      </div>
      <Textarea
        className="automation-json-editor__textarea"
        value={value}
        readOnly={readOnly}
        onChange={(event) => onChange?.(event.target.value)}
        spellCheck={false}
        style={{ minHeight }}
      />
      {error && <div className="automation-json-editor__error">{error}</div>}
    </div>
  );
}

export function AutomationJsonTreeViewer({ label, value }: { label: string; value: unknown }) {
  return <JsonTreeViewer label={label} value={value} />;
}
