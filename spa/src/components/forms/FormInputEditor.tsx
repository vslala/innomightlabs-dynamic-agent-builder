import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { FieldGroup } from "../layout";
import { Button, Input, Label, Select, SelectContent, SelectItem, SelectTrigger, SelectValue, Switch, Textarea } from "../ui";
import type { FormInput } from "../../types/form";
import {
  FORM_INPUT_KINDS,
  inputNameFrom,
  isOptional,
  kindById,
  kindOf,
  withAttr,
  withOptional,
} from "./formInputKinds";
import styles from "./FormInputEditor.module.css";

const PLACEHOLDER_NAME = /^field(_\d+)?$/;

interface FormInputEditorProps {
  inputs: FormInput[];
  onChange: (inputs: FormInput[]) => void;
  disabled?: boolean;
  /** Ask for guidance the agent reads when it fills the form in (`attr.agent_hint`). */
  agentHints?: boolean;
}

/** Edits a list of the platform's `FormInput`s. The API validates what is saved; this only shapes it. */
export function FormInputEditor({ inputs, onChange, disabled = false, agentHints = false }: FormInputEditorProps) {
  const replace = (index: number, input: FormInput) => onChange(inputs.map((existing, at) => (at === index ? input : existing)));
  const remove = (index: number) => onChange(inputs.filter((_, at) => at !== index));
  const move = (index: number, by: -1 | 1) => {
    const next = [...inputs];
    [next[index], next[index + by]] = [next[index + by], next[index]];
    onChange(next);
  };
  const add = () => {
    const taken = new Set(inputs.map((input) => input.name));
    let name = "field";
    for (let n = 2; taken.has(name); n++) name = `field_${n}`;
    onChange([...inputs, { input_type: "text", name, label: "New field" }]);
  };

  return (
    <div className={styles.editor}>
      {inputs.map((input, index) => (
        <InputRow
          key={index}
          input={input}
          disabled={disabled}
          agentHints={agentHints}
          onChange={(updated) => replace(index, updated)}
          onRemove={() => remove(index)}
          onMoveUp={index > 0 ? () => move(index, -1) : undefined}
          onMoveDown={index < inputs.length - 1 ? () => move(index, 1) : undefined}
        />
      ))}
      <Button type="button" variant="outline" size="sm" disabled={disabled} onClick={add} className={styles.add}>
        <Plus aria-hidden="true" />
        Add field
      </Button>
    </div>
  );
}

interface InputRowProps {
  input: FormInput;
  disabled: boolean;
  agentHints: boolean;
  onChange: (input: FormInput) => void;
  onRemove: () => void;
  onMoveUp?: () => void;
  onMoveDown?: () => void;
}

function InputRow({ input, disabled, agentHints, onChange, onRemove, onMoveUp, onMoveDown }: InputRowProps) {
  const kind = kindOf(input);
  const id = (part: string) => `field-${input.name}-${part}`;
  const options = (input.options ?? []).map((option) => option.label).join("\n");

  return (
    <fieldset className={styles.row} disabled={disabled}>
      <legend className={styles.legend}>{input.label || "Untitled field"}</legend>
      <div className={styles.grid}>
        <FieldGroup>
          <Label htmlFor={id("label")}>Label</Label>
          <Input
            id={id("label")}
            value={input.label}
            onChange={(e) => onChange({ ...input, label: e.target.value })}
            onBlur={() => {
              // A new field takes its name from its label, until someone names it themselves
              if (PLACEHOLDER_NAME.test(input.name)) onChange({ ...input, name: inputNameFrom(input.label) });
            }}
          />
        </FieldGroup>
        <FieldGroup>
          <Label htmlFor={id("name")}>Field name</Label>
          <Input
            id={id("name")}
            value={input.name}
            onChange={(e) => onChange({ ...input, name: e.target.value })}
            className={styles.mono}
          />
        </FieldGroup>
        <FieldGroup>
          <Label htmlFor={id("kind")}>Type</Label>
          <Select value={kind.id} onValueChange={(next) => onChange(kindById(next).shape(input))}>
            <SelectTrigger id={id("kind")}><SelectValue /></SelectTrigger>
            <SelectContent>
              {FORM_INPUT_KINDS.map((option) => (
                <SelectItem key={option.id} value={option.id}>{option.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FieldGroup>
        <label className={styles.required}>
          <Switch
            checked={!isOptional(input)}
            onCheckedChange={(required) => onChange(withOptional(input, !required))}
            aria-label="Required"
          />
          Required
        </label>
      </div>

      {kind.hasOptions && (
        <FieldGroup>
          <Label htmlFor={id("options")}>Options, one per line</Label>
          <Textarea
            id={id("options")}
            rows={3}
            value={options}
            onChange={(e) => {
              const labels = e.target.value.split("\n");
              onChange({ ...input, options: labels.map((label) => ({ value: label.trim(), label: label.trim() })) });
            }}
            onBlur={() => onChange({ ...input, options: (input.options ?? []).filter((option) => option.value) })}
          />
        </FieldGroup>
      )}

      {kind.id === "file" && (
        <FieldGroup>
          <Label htmlFor={id("files")}>Files a person may upload</Label>
          <Input
            id={id("files")}
            type="number"
            min={1}
            max={5}
            value={input.validation?.max_items ?? 1}
            onChange={(e) => onChange({ ...input, validation: { ...input.validation, max_items: Number(e.target.value) || 1 } })}
            className={styles.narrow}
          />
        </FieldGroup>
      )}

      <div className={styles.grid}>
        <FieldGroup>
          <Label htmlFor={id("help")}>Help for the person filling it in</Label>
          <Input
            id={id("help")}
            value={input.attr?.help_text ?? ""}
            onChange={(e) => onChange(withAttr(input, "help_text", e.target.value))}
          />
        </FieldGroup>
        {agentHints && (
          <FieldGroup>
            <Label htmlFor={id("hint")}>Guidance for the agent</Label>
            <Input
              id={id("hint")}
              value={input.attr?.agent_hint ?? ""}
              placeholder="e.g. Ask only after you have helped them"
              onChange={(e) => onChange(withAttr(input, "agent_hint", e.target.value))}
            />
          </FieldGroup>
        )}
      </div>

      <div className={styles.rowActions}>
        <Button type="button" variant="ghost" size="icon" aria-label={`Move ${input.label} up`} disabled={!onMoveUp} onClick={onMoveUp}>
          <ArrowUp aria-hidden="true" />
        </Button>
        <Button type="button" variant="ghost" size="icon" aria-label={`Move ${input.label} down`} disabled={!onMoveDown} onClick={onMoveDown}>
          <ArrowDown aria-hidden="true" />
        </Button>
        <Button type="button" variant="ghost" size="icon" aria-label={`Remove ${input.label}`} onClick={onRemove}>
          <Trash2 aria-hidden="true" />
        </Button>
      </div>
    </fieldset>
  );
}
