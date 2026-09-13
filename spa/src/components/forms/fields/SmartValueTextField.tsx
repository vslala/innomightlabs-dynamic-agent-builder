/**
 * Text field that understands smart values.
 *
 * Typing `{{` opens a picker filtered by what follows it; choosing an entry
 * inserts a complete token. Tokens already in the value are listed underneath
 * with the value they resolved to in the selected run, so a reference that no
 * longer exists is visible without running the automation.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Braces, Eye, TriangleAlert } from "lucide-react";

import { Button } from "../../ui/button";
import { Input } from "../../ui/input";
import { Textarea } from "../../ui/textarea";
import {
  findSuggestion,
  useOptionalSmartValues,
  type SmartValueSuggestion,
  type SmartValueSuggestionGroup,
} from "../SmartValueContext";
import {
  insertTokenAt,
  isUnknownPath,
  openTokenQuery,
  parseTokenPaths,
  tokenFor,
} from "../smartValueTokens";
import styles from "./SmartValueTextField.module.css";
import type { FormInput, FormValue } from "../../../types/form";

interface Props {
  field: FormInput;
  value: FormValue;
  onChange: (value: FormValue) => void;
  multiline?: boolean;
}

interface Flat {
  group: SmartValueSuggestionGroup;
  field: SmartValueSuggestion;
}

const MAX_SUGGESTIONS = 40;

export function SmartValueTextField({ field, value, onChange, multiline = false }: Props) {
  const smartValues = useOptionalSmartValues();
  const text = typeof value === "string" ? value : "";
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const [highlight, setHighlight] = useState(0);
  const [preview, setPreview] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);

  const groups = useMemo(() => smartValues?.groups ?? [], [smartValues]);
  const suggestions = useMemo(() => flatten(groups, filter), [filter, groups]);

  useEffect(() => setHighlight(0), [filter, pickerOpen]);

  const fieldId = `${field.name}-smart`;

  // Register as the insert target so a run output tree can write into the field
  // the user last touched.
  useEffect(() => {
    if (!smartValues) return;
    return () => smartValues.clearTarget(fieldId);
  }, [fieldId, smartValues]);

  const insertToken = (token: string) => {
    const element = inputRef.current;
    const start = element?.selectionStart ?? text.length;
    const end = element?.selectionEnd ?? text.length;
    const { value: next, cursor } = insertTokenAt(text, start, end, token);
    onChange(next);
    setPickerOpen(false);
    setFilter("");
    window.requestAnimationFrame(() => {
      const node = inputRef.current;
      if (!node) return;
      node.focus();
      node.setSelectionRange(cursor, cursor);
    });
  };

  const handleChange = (next: string) => {
    onChange(next);
    if (!smartValues) return;
    const element = inputRef.current;
    const caret = element?.selectionStart ?? next.length;
    const open = openTokenQuery(next.slice(0, caret));
    if (open === null) {
      setPickerOpen(false);
      setFilter("");
      return;
    }
    setPickerOpen(true);
    setFilter(open);
  };

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (!pickerOpen || suggestions.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlight((current) => (current + 1) % suggestions.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlight((current) => (current - 1 + suggestions.length) % suggestions.length);
    } else if (event.key === "Enter" || event.key === "Tab") {
      event.preventDefault();
      insertToken(tokenFor(suggestions[highlight].field.path));
    } else if (event.key === "Escape") {
      event.preventDefault();
      setPickerOpen(false);
    }
  };

  const runPreview = async () => {
    if (!smartValues?.preview) return;
    setPreviewing(true);
    try {
      setPreview(await smartValues.preview(text));
    } catch {
      setPreview(null);
    } finally {
      setPreviewing(false);
    }
  };

  const control = multiline ? (
    <Textarea
      ref={inputRef as React.Ref<HTMLTextAreaElement>}
      id={field.name}
      name={field.name}
      rows={Number(field.attr?.rows ?? 5)}
      value={text}
      placeholder={field.attr?.placeholder ?? `Enter ${field.label.toLowerCase()}`}
      onChange={(event) => handleChange(event.target.value)}
      onKeyDown={handleKeyDown}
      onFocus={() => smartValues?.setTarget({ id: fieldId, label: field.label, insert: insertToken })}
    />
  ) : (
    <Input
      ref={inputRef as React.Ref<HTMLInputElement>}
      id={field.name}
      name={field.name}
      value={text}
      placeholder={field.attr?.placeholder ?? `Enter ${field.label.toLowerCase()}`}
      onChange={(event) => handleChange(event.target.value)}
      onKeyDown={handleKeyDown}
      onFocus={() => smartValues?.setTarget({ id: fieldId, label: field.label, insert: insertToken })}
    />
  );

  if (!smartValues) return control;

  return (
    <div className={styles.wrapper}>
      {control}

      <div className={styles.toolbar}>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => {
            setFilter("");
            setPickerOpen((open) => !open);
          }}
          title="Insert a value from a previous step"
        >
          <Braces className="h-3.5 w-3.5" />
          Insert value
        </Button>
        {smartValues.preview && text.includes("{{") && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => void runPreview()}
            disabled={previewing}
            title="Render this field using the selected run"
          >
            <Eye className="h-3.5 w-3.5" />
            {previewing ? "Rendering…" : "Preview"}
          </Button>
        )}
      </div>

      {pickerOpen && (
        <div className={styles.picker} role="listbox">
          {suggestions.length === 0 ? (
            <p className={styles.pickerEmpty}>
              No values match{filter ? ` “${filter}”` : ""}. Earlier steps appear here once they exist.
            </p>
          ) : (
            renderGroups(suggestions, highlight, insertToken)
          )}
        </div>
      )}

      <TokenList text={text} groups={groups} />

      {preview !== null && (
        <div className={styles.preview}>
          <span className={styles.previewLabel}>Rendered with the selected run</span>
          <pre>{preview || "(empty)"}</pre>
        </div>
      )}
    </div>
  );
}

function renderGroups(
  suggestions: Flat[],
  highlight: number,
  onPick: (token: string) => void
) {
  const rows: React.ReactNode[] = [];
  let lastGroup = "";
  suggestions.forEach((entry, index) => {
    if (entry.group.id !== lastGroup) {
      lastGroup = entry.group.id;
      rows.push(
        <div className={styles.groupHeader} key={`group-${entry.group.id}`}>
          <strong>{entry.group.label}</strong>
          {entry.group.subtitle ? <small>{entry.group.subtitle}</small> : null}
        </div>
      );
    }
    rows.push(
      <Button
        key={entry.field.path}
        type="button"
        variant="ghost"
        className={index === highlight ? `${styles.option} ${styles.optionActive}` : styles.option}
        onClick={() => onPick(tokenFor(entry.field.path))}
        role="option"
        aria-selected={index === highlight}
      >
        <span className={styles.optionText}>
          <strong>{entry.field.label}</strong>
          <code>{entry.field.path}</code>
          {entry.field.sample ? <small>{entry.field.sample}</small> : null}
        </span>
      </Button>
    );
  });
  return rows;
}

function TokenList({
  text,
  groups,
}: {
  text: string;
  groups: SmartValueSuggestionGroup[];
}) {
  const tokens = useMemo(() => parseTokenPaths(text), [text]);
  if (tokens.length === 0) return null;

  return (
    <div className={styles.tokens}>
      {tokens.map((path, index) => {
        const suggestion = findSuggestion(groups, path);
        const unknown = isUnknownPath(path, groups);
        return (
          <span
            key={`${path}-${index}`}
            className={unknown ? `${styles.token} ${styles.tokenUnknown}` : styles.token}
            title={
              unknown
                ? "This reference does not match any step in this automation."
                : suggestion?.sample ?? path
            }
          >
            {unknown && <TriangleAlert className="h-3 w-3" />}
            <code>{path}</code>
            {suggestion?.sample ? <em>{suggestion.sample}</em> : null}
          </span>
        );
      })}
    </div>
  );
}

function flatten(groups: SmartValueSuggestionGroup[], filter: string): Flat[] {
  const terms = filter.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const flat: Flat[] = [];
  groups.forEach((group) => {
    group.fields.forEach((field) => {
      const haystack = `${group.label} ${field.label} ${field.path}`.toLowerCase();
      if (terms.every((term) => haystack.includes(term))) flat.push({ group, field });
    });
  });
  return flat.slice(0, MAX_SUGGESTIONS);
}

