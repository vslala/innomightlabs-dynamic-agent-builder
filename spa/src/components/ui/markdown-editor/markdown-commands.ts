/**
 * The toolbar's formatting, as plain text edits: each takes the document and the selection and returns the one
 * change to make and where the selection lands. Nothing here knows about CodeMirror, so it is tested directly.
 *
 * Every command writes ordinary Markdown into the text. The editor never converts the document into another
 * model, so what is saved is exactly what was typed (agent instructions are sent to the model as they are).
 */

export interface TextChange {
  from: number;
  to: number;
  insert: string;
}

export interface Edit {
  change: TextChange;
  selection: { anchor: number; head: number };
}

/** `**bold**`, `*italic*`, `` `code` ``: wrap the selection, or unwrap it if it is already wrapped. */
export function toggleWrap(doc: string, from: number, to: number, marker: string, placeholder: string): Edit {
  const before = doc.slice(from - marker.length, from);
  const after = doc.slice(to, to + marker.length);
  if (from !== to && before === marker && after === marker) {
    return {
      change: { from: from - marker.length, to: to + marker.length, insert: doc.slice(from, to) },
      selection: { anchor: from - marker.length, head: to - marker.length },
    };
  }
  const text = from === to ? placeholder : doc.slice(from, to);
  return {
    change: { from, to, insert: `${marker}${text}${marker}` },
    selection: { anchor: from + marker.length, head: from + marker.length + text.length },
  };
}

export type LinePrefix = "heading" | "bullet" | "number" | "quote";

const PREFIXES: Record<LinePrefix, { pattern: RegExp; make: (index: number) => string }> = {
  heading: { pattern: /^#{1,6} /, make: () => "## " },
  bullet: { pattern: /^[-*+] /, make: () => "- " },
  number: { pattern: /^\d+\. /, make: (index) => `${index + 1}. ` },
  quote: { pattern: /^> /, make: () => "> " },
};

/**
 * Turn every line the selection touches into a heading, bullet, numbered item or quote. If they all already
 * are one, remove it instead. Another kind of prefix already on a line is replaced, not stacked.
 */
export function toggleLinePrefix(doc: string, from: number, to: number, kind: LinePrefix): Edit {
  const start = doc.lastIndexOf("\n", from - 1) + 1;
  const endBreak = doc.indexOf("\n", to);
  const end = endBreak === -1 ? doc.length : endBreak;
  const lines = doc.slice(start, end).split("\n");
  const { pattern, make } = PREFIXES[kind];
  const allHave = lines.every((line) => pattern.test(line));
  const anyPrefix = /^(#{1,6} |[-*+] |\d+\. |> )/;

  const next = lines
    .map((line, index) => (allHave ? line.replace(pattern, "") : make(index) + line.replace(anyPrefix, "")))
    .join("\n");

  return {
    change: { from: start, to: end, insert: next },
    selection: { anchor: start, head: start + next.length },
  };
}

/** `[text](url)`, with the url selected so it can be typed over. */
export function insertLink(doc: string, from: number, to: number): Edit {
  const text = from === to ? "link text" : doc.slice(from, to);
  const insert = `[${text}](https://)`;
  const urlStart = from + text.length + 3;
  return {
    change: { from, to, insert },
    selection: { anchor: urlStart, head: urlStart + "https://".length },
  };
}

/** Apply an edit to a string: what the document becomes. Used by tests and by nothing else. */
export function applyEdit(doc: string, edit: Edit): string {
  return doc.slice(0, edit.change.from) + edit.change.insert + doc.slice(edit.change.to);
}
