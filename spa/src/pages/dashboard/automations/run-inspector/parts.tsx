/**
 * Building blocks of the run inspector: a titled section, a copy button, text that folds when long, and a
 * key/value list of arguments or results.
 *
 * Nothing here trims content. Long text is folded behind "Show all" but stays in the page whole, so the browser's
 * find and copy still see every character.
 */

import { useState, type ReactNode } from "react";
import { Check, Copy } from "lucide-react";

import { Button } from "../../../../components/ui";
import { asText } from "./toolCalls";

const FOLD_AFTER_CHARS = 600;
const FOLD_AFTER_LINES = 10;

export function InspectorSection({
  title,
  actions,
  children,
}: {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="run-inspector-section">
      <header className="run-inspector-section__bar">
        <h4>{title}</h4>
        {actions}
      </header>
      <div className="run-inspector-section__body">{children}</div>
    </section>
  );
}

export function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className="run-inspector-copy"
      aria-label={copied ? `${label}: copied` : label}
      title={label}
      onClick={() => void copy()}
    >
      {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
    </Button>
  );
}

export function ExpandableText({ text, mono = false }: { text: string; mono?: boolean }) {
  const long = text.length > FOLD_AFTER_CHARS || text.split("\n").length > FOLD_AFTER_LINES;
  const [expanded, setExpanded] = useState(false);
  const folded = long && !expanded;

  return (
    <div className="run-inspector-text">
      <div
        className={[
          "run-inspector-text__content",
          mono ? "run-inspector-text__content--mono" : "",
          folded ? "run-inspector-text__content--folded" : "",
        ].join(" ")}
      >
        {text}
      </div>
      {long && (
        <Button
          type="button"
          variant="link"
          size="sm"
          className="run-inspector-text__toggle"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? "Show less" : `Show all · ${text.length.toLocaleString()} characters`}
        </Button>
      )}
    </div>
  );
}

/** Each top-level field on its own row, its value whole (objects as indented JSON). */
export function ValueList({ value, empty }: { value: Record<string, unknown>; empty: string }) {
  const entries = Object.entries(value);
  if (entries.length === 0) return <p className="run-inspector-muted">{empty}</p>;

  return (
    <dl className="run-inspector-values">
      {entries.map(([key, item]) => (
        <div key={key} className="run-inspector-values__row">
          <dt>{key}</dt>
          <dd>
            <ExpandableText text={asText(item)} mono={typeof item !== "string"} />
          </dd>
        </div>
      ))}
    </dl>
  );
}
