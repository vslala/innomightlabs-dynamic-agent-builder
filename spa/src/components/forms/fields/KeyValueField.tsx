import { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Button } from "../../ui/button";
import { Input } from "../../ui/input";
import type { FormInput, FormValue, KeyValueFormValue } from "../../../types/form";

interface Props {
  field: FormInput;
  value: FormValue;
  onChange: (value: FormValue) => void;
}

interface Row {
  key: string;
  value: string;
}

function isKeyValue(value: FormValue): value is KeyValueFormValue {
  return value !== null && typeof value === "object" && !(value instanceof FileList) && !Array.isArray(value);
}

function toRows(value: FormValue): Row[] {
  if (!isKeyValue(value)) return [];
  const rows = Object.entries(value).map(([key, rowValue]) => ({ key, value: String(rowValue) }));
  return rows;
}

function toValue(rows: Row[]): KeyValueFormValue {
  return Object.fromEntries(
    rows
      .map((row) => [row.key.trim(), row.value] as const)
      .filter(([key]) => key.length > 0)
  );
}

export function KeyValueField({ field, value, onChange }: Props) {
  const fieldAttributes = field.attr || {};
  const [rows, setRows] = useState<Row[]>(() => toRows(value));

  useEffect(() => {
    setRows(toRows(value));
  }, [field.name]);

  const updateRows = (nextRows: Row[]) => {
    setRows(nextRows);
    onChange(toValue(nextRows));
  };

  return (
    <div className="flex flex-col gap-3">
      {rows.length === 0 && (
        <div className="rounded-lg border border-dashed border-[var(--border-subtle)] bg-white/5 px-3 py-2 text-sm text-[var(--text-muted)]">
          {fieldAttributes.empty_text || "No input values configured."}
        </div>
      )}

      {rows.map((row, index) => (
        <div key={`${field.name}-${index}`} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_2.5rem] gap-2">
          <Input
            aria-label={`${field.label} key ${index + 1}`}
            value={row.key}
            onChange={(event) => {
              const nextRows = [...rows];
              nextRows[index] = { ...row, key: event.target.value };
              updateRows(nextRows);
            }}
            placeholder={fieldAttributes.key_placeholder || "Key"}
          />
          <Input
            aria-label={`${field.label} value ${index + 1}`}
            value={row.value}
            onChange={(event) => {
              const nextRows = [...rows];
              nextRows[index] = { ...row, value: event.target.value };
              updateRows(nextRows);
            }}
            placeholder={fieldAttributes.value_placeholder || "Value"}
          />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={`Remove ${field.label} row ${index + 1}`}
            onClick={() => updateRows(rows.filter((_, rowIndex) => rowIndex !== index))}
          >
            <Trash2 />
          </Button>
        </div>
      ))}

      <Button
        type="button"
        variant="outline"
        size="sm"
        className="self-start"
        onClick={() => setRows([...rows, { key: "", value: "" }])}
      >
        <Plus />
        {fieldAttributes.add_label || "Add field"}
      </Button>
    </div>
  );
}
