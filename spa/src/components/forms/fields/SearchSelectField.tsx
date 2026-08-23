import { useMemo, useState } from "react";
import { Check, ChevronDown } from "lucide-react";

import { Button } from "../../ui/button";
import { SearchInput } from "../../ui/search-input";
import type { FormInput, FormValue } from "../../../types/form";

interface Props {
  field: FormInput;
  value: FormValue;
  onChange: (value: FormValue) => void;
}

function normalizedOptions(field: FormInput) {
  return field.options
    ? field.options.map((opt) => ({ value: opt.value, label: opt.label }))
    : field.values?.map((v) => ({ value: v, label: v })) || [];
}

export function SearchSelectField({ field, value, onChange }: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const selectedValue = typeof value === "string" ? value : "";
  const selectOptions = useMemo(() => normalizedOptions(field), [field]);
  const selectedOption = selectOptions.find((option) => option.value === selectedValue);
  const normalizedQuery = query.trim().toLowerCase();
  const filteredOptions = normalizedQuery
    ? selectOptions.filter((option) =>
        `${option.label} ${option.value}`.toLowerCase().includes(normalizedQuery)
      )
    : selectOptions;

  const placeholder = `Select ${field.label.toLowerCase()}`;

  return (
    <div style={{ position: "relative", width: "100%" }}>
      <Button
        type="button"
        variant="outline"
        onClick={() => setIsOpen((open) => !open)}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        style={{
          width: "100%",
          justifyContent: "space-between",
          minHeight: "var(--control-height-md)",
          paddingInline: "var(--control-padding-x-sm)",
          textAlign: "left",
        }}
      >
        <span
          style={{
            minWidth: 0,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            color: selectedOption ? "var(--text-primary)" : "var(--text-muted)",
          }}
        >
          {selectedOption?.label ?? placeholder}
        </span>
        <ChevronDown aria-hidden="true" style={{ height: 16, width: 16, opacity: 0.5 }} />
      </Button>

      {isOpen && (
        <div
          className="shadow-xl"
          role="listbox"
          aria-label={field.label}
          style={{
            position: "absolute",
            zIndex: 50,
            top: "calc(100% + var(--space-1))",
            left: 0,
            right: 0,
            maxHeight: 320,
            overflow: "hidden",
            border: "1px solid var(--border-default)",
            borderRadius: "var(--radius-lg)",
            background: "var(--surface-popover)",
            padding: "var(--space-2)",
          }}
        >
          <SearchInput
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={`Search ${field.label.toLowerCase()}`}
            autoFocus
          />
          <div
            style={{
              marginTop: "var(--space-2)",
              maxHeight: 240,
              overflowY: "auto",
            }}
          >
            {filteredOptions.length === 0 ? (
              <div style={{ padding: "var(--space-3)", color: "var(--text-muted)", fontSize: "0.875rem" }}>
                No options found
              </div>
            ) : (
              filteredOptions.map((option) => {
                const selected = option.value === selectedValue;
                return (
                  <button
                    key={option.value}
                    type="button"
                    role="option"
                    aria-selected={selected}
                    onClick={() => {
                      onChange(option.value);
                      setIsOpen(false);
                      setQuery("");
                    }}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "var(--space-2)",
                      width: "100%",
                      minHeight: 36,
                      border: "none",
                      borderRadius: "var(--radius-md)",
                      background: selected ? "var(--bg-tertiary)" : "transparent",
                      color: "var(--text-primary)",
                      cursor: "pointer",
                      padding: "var(--space-2) var(--space-3)",
                      textAlign: "left",
                    }}
                  >
                    <span style={{ width: 16, display: "inline-flex" }}>
                      {selected && <Check aria-hidden="true" style={{ height: 16, width: 16 }} />}
                    </span>
                    <span
                      style={{
                        minWidth: 0,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {option.label}
                    </span>
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
