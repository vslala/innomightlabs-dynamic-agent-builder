/**
 * Structured conditions, compiled to the expression grammar the runner supports.
 *
 * The backend evaluator understands exactly three shapes: a truthy path, an
 * equality, and an inequality (api/src/automations/smart_values.py). The editor
 * offers only those, so a condition built here always means what it says.
 * Anything hand-written that does not parse is preserved and shown as raw text.
 */

export type ConditionOperator = "truthy" | "eq" | "ne";

export interface StructuredCondition {
  kind: "structured";
  left: string;
  operator: ConditionOperator;
  right: string;
}

export interface RawCondition {
  kind: "raw";
  expression: string;
}

export type ParsedCondition = StructuredCondition | RawCondition;

export const CONDITION_OPERATORS: { value: ConditionOperator; label: string; needsRight: boolean }[] = [
  { value: "truthy", label: "has a value", needsRight: false },
  { value: "eq", label: "is equal to", needsRight: true },
  { value: "ne", label: "is not equal to", needsRight: true },
];

const PATH_PATTERN = /^[A-Za-z$][A-Za-z0-9_.$-]*$/;

export function compileCondition(condition: StructuredCondition): string {
  const left = condition.left.trim();
  if (!left) return "";
  if (condition.operator === "truthy") return left;
  const operator = condition.operator === "eq" ? "==" : "!=";
  return `${left} ${operator} ${quote(condition.right)}`;
}

export function parseCondition(expression: string): ParsedCondition {
  const trimmed = (expression ?? "").trim();
  if (!trimmed) return { kind: "structured", left: "", operator: "truthy", right: "" };

  for (const [token, operator] of [["==", "eq"], ["!=", "ne"]] as const) {
    const index = indexOutsideQuotes(trimmed, token);
    if (index === -1) continue;
    const left = trimmed.slice(0, index).trim();
    const right = trimmed.slice(index + token.length).trim();
    if (!PATH_PATTERN.test(left)) return { kind: "raw", expression: trimmed };
    return { kind: "structured", left, operator, right: unquote(right) };
  }

  if (PATH_PATTERN.test(trimmed)) {
    return { kind: "structured", left: trimmed, operator: "truthy", right: "" };
  }
  return { kind: "raw", expression: trimmed };
}

/** Human-readable form for the collapsed card, e.g. `gmail_search.output.result has a value`. */
export function describeParsedCondition(expression: string): string | null {
  const parsed = parseCondition(expression);
  if (parsed.kind === "raw") return parsed.expression;
  if (!parsed.left) return null;
  const operator = CONDITION_OPERATORS.find((item) => item.value === parsed.operator);
  const label = operator?.label ?? parsed.operator;
  return operator?.needsRight
    ? `${parsed.left} ${label} ${parsed.right || '""'}`
    : `${parsed.left} ${label}`;
}

function quote(value: string): string {
  const trimmed = value.trim();
  if (trimmed === "true" || trimmed === "false" || trimmed === "null") return trimmed;
  if (trimmed !== "" && Number.isFinite(Number(trimmed))) return trimmed;
  return `"${trimmed.replace(/"/g, '\\"')}"`;
}

function unquote(value: string): string {
  const trimmed = value.trim();
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"') && trimmed.length >= 2) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'") && trimmed.length >= 2)
  ) {
    return trimmed.slice(1, -1).replace(/\\"/g, '"');
  }
  return trimmed;
}

function indexOutsideQuotes(text: string, token: string): number {
  let quoteChar: string | null = null;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (quoteChar) {
      if (char === quoteChar) quoteChar = null;
      continue;
    }
    if (char === '"' || char === "'") {
      quoteChar = char;
      continue;
    }
    if (text.startsWith(token, index)) return index;
  }
  return -1;
}
