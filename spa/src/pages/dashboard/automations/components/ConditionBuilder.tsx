/**
 * Structured editor for an IF/ELSE step.
 *
 * The left side is picked from the smart value catalog rather than typed, so a
 * condition references a real step output instead of a guessed path.
 */

import { useMemo, useState } from "react";

import {
  Button,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../../../components/ui";
import type { SmartValueGroup } from "../chain/smartValues";
import {
  CONDITION_OPERATORS,
  compileCondition,
  parseCondition,
  type ConditionOperator,
} from "../chain/conditionExpression";

export function ConditionBuilder({
  expression,
  groups,
  disabled,
  onChange,
}: {
  expression: string;
  groups: SmartValueGroup[];
  disabled: boolean;
  onChange: (expression: string) => void;
}) {
  const parsed = useMemo(() => parseCondition(expression), [expression]);
  const [raw, setRaw] = useState(parsed.kind === "raw");

  const options = useMemo(
    () =>
      groups.flatMap((group) =>
        group.fields.map((field) => ({
          value: field.path,
          label: `${group.label} · ${field.label}`,
          sample: field.sample,
        }))
      ),
    [groups]
  );

  if (raw || parsed.kind === "raw") {
    return (
      <div className="chain-field">
        <Label htmlFor="condition-raw">Condition</Label>
        <Input
          id="condition-raw"
          value={parsed.kind === "raw" ? parsed.expression : expression}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
          placeholder="steps.gmail_search.status == &quot;succeeded&quot;"
        />
        <p className="chain-field__hint">
          Supports a value on its own, or a comparison with <code>==</code> or <code>!=</code>.
          {parsed.kind !== "raw" && (
            <Button type="button" variant="ghost" size="sm" onClick={() => setRaw(false)}>
              Use the guided editor
            </Button>
          )}
        </p>
      </div>
    );
  }

  const structured = parsed;
  const operator = CONDITION_OPERATORS.find((item) => item.value === structured.operator);
  const selected = options.find((option) => option.value === structured.left);

  const update = (next: Partial<typeof structured>) =>
    onChange(compileCondition({ ...structured, ...next }));

  return (
    <div className="chain-condition">
      <div className="chain-field">
        <Label>Check this value</Label>
        <Select
          value={structured.left || undefined}
          onValueChange={(value) => update({ left: value })}
          disabled={disabled || options.length === 0}
        >
          <SelectTrigger>
            <SelectValue placeholder={options.length ? "Pick a value" : "Add a step above first"} />
          </SelectTrigger>
          <SelectContent>
            {options.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
            {structured.left && !selected && (
              <SelectItem value={structured.left}>{structured.left}</SelectItem>
            )}
          </SelectContent>
        </Select>
        {selected?.sample ? (
          <p className="chain-field__hint">Last run: {selected.sample}</p>
        ) : null}
      </div>

      <div className="chain-field">
        <Label>Comparison</Label>
        <Select
          value={structured.operator}
          onValueChange={(value) => update({ operator: value as ConditionOperator })}
          disabled={disabled}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {CONDITION_OPERATORS.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {operator?.needsRight && (
        <div className="chain-field">
          <Label htmlFor="condition-right">Value</Label>
          <Input
            id="condition-right"
            value={structured.right}
            disabled={disabled}
            onChange={(event) => update({ right: event.target.value })}
            placeholder="succeeded"
          />
        </div>
      )}

      <Button type="button" variant="ghost" size="sm" onClick={() => setRaw(true)}>
        Write it by hand
      </Button>
    </div>
  );
}
