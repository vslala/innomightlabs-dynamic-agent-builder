/**
 * Test sheet.
 *
 * The manual input form is generated from the `{{ input.* }}` references the
 * graph actually uses, so the common case is filling in named fields rather than
 * hand-writing JSON. The raw editor stays available for anything the scan misses.
 */

import { useMemo, useState } from "react";
import { Braces, Loader2, Play, X } from "lucide-react";

import { Button, Input, Label } from "../../../../components/ui";
import type { AutomationGraphResponse } from "../../../../types/automation";
import { detectInputKeys } from "../chain/smartValues";
import { AutomationJsonEditor } from "./AutomationJsonEditor";

export function TestPanel({
  graph,
  open,
  running,
  error,
  onClose,
  onRun,
}: {
  graph: AutomationGraphResponse;
  open: boolean;
  running: boolean;
  error: string | null;
  onClose: () => void;
  onRun: (input: Record<string, unknown>) => void;
}) {
  const keys = useMemo(() => detectInputKeys(graph), [graph]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [raw, setRaw] = useState('{\n  "input": ""\n}');
  const [rawError, setRawError] = useState<string | null>(null);
  // Raw JSON is the default only while the graph declares no named inputs;
  // once the user chooses a mode explicitly, that choice wins.
  const [rawChoice, setRawChoice] = useState<boolean | null>(null);
  const rawMode = rawChoice ?? keys.length === 0;

  if (!open) return null;

  const run = () => {
    if (!rawMode) {
      onRun(Object.fromEntries(keys.map((key) => [key, values[key] ?? ""])));
      return;
    }
    try {
      onRun(JSON.parse(raw) as Record<string, unknown>);
      setRawError(null);
    } catch (parseError) {
      setRawError(parseError instanceof Error ? parseError.message : "Invalid JSON");
    }
  };

  return (
    <aside className="automation-test">
      <div className="automation-test__head">
        <div>
          <h3>Test this automation</h3>
          <p>Runs the saved workflow once and shows the result on the steps.</p>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close test panel">
          <X className="h-4 w-4" />
        </Button>
      </div>

      {error ? <div className="automation-test__error">{error}</div> : null}

      <div className="automation-test__body">
        {rawMode ? (
          <AutomationJsonEditor
            label="Manual input"
            value={raw}
            error={rawError}
            minHeight="9rem"
            onChange={(next) => {
              setRaw(next);
              setRawError(null);
            }}
            onFormat={() => {
              try {
                setRaw(JSON.stringify(JSON.parse(raw), null, 2));
                setRawError(null);
              } catch (formatError) {
                setRawError(formatError instanceof Error ? formatError.message : "Invalid JSON");
              }
            }}
          />
        ) : (
          <div className="automation-test__fields">
            {keys.map((key) => (
              <div className="chain-field" key={key}>
                <Label htmlFor={`test-${key}`}>{humanize(key)}</Label>
                <Input
                  id={`test-${key}`}
                  value={values[key] ?? ""}
                  placeholder={`{{ input.${key} }}`}
                  onChange={(event) =>
                    setValues((current) => ({ ...current, [key]: event.target.value }))
                  }
                />
              </div>
            ))}
          </div>
        )}

        {keys.length > 0 && (
          <Button variant="ghost" size="sm" onClick={() => setRawChoice(!rawMode)}>
            <Braces className="h-3.5 w-3.5" />
            {rawMode ? "Use the generated fields" : "Edit raw JSON"}
          </Button>
        )}
      </div>

      <div className="automation-test__actions">
        <Button onClick={run} disabled={running}>
          {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          {running ? "Running…" : "Run test"}
        </Button>
      </div>
    </aside>
  );
}

function humanize(key: string): string {
  return key
    .replace(/[_-]+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}
