/**
 * The Markdown editor proper: CodeMirror 6 with live styling. Headings are set large, emphasis is shown as
 * emphasis, lists and quotes are coloured, and `{{ ... }}` macros and smart values read as chips. The text
 * itself is never converted: what is typed is what is saved.
 *
 * Loaded lazily through `index.tsx`, so CodeMirror is only downloaded when someone edits.
 */

import { useEffect, useRef, type ReactNode } from "react";
import { Bold, Code, Heading2, Italic, Link2, List, ListOrdered, Quote } from "lucide-react";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { HighlightStyle, Language, LanguageSupport, defineLanguageFacet, syntaxHighlighting } from "@codemirror/language";
import { EditorState, type Extension } from "@codemirror/state";
import {
  Decoration,
  EditorView,
  MatchDecorator,
  ViewPlugin,
  keymap,
  placeholder as placeholderExtension,
  type DecorationSet,
  type ViewUpdate,
} from "@codemirror/view";
import { tags } from "@lezer/highlight";
import { GFM, parser as markdownParser } from "@lezer/markdown";

import { Button } from "../button";
import { insertLink, toggleLinePrefix, toggleWrap, type Edit, type LinePrefix } from "./markdown-commands";
import styles from "./markdown-editor.module.css";
import type { MarkdownEditorProps } from "./types";

const LINE_HEIGHT_REM = 1.6;

export default function MarkdownEditorView({
  id,
  value,
  onChange,
  placeholder,
  minRows = 8,
  disabled = false,
  ariaLabelledBy,
  ariaLabel,
}: MarkdownEditorProps) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  // The latest onChange, so the editor (created once) never calls a stale one
  const onChangeRef = useRef(onChange);
  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  useEffect(() => {
    if (!host.current) return;
    const editor = new EditorView({
      parent: host.current,
      state: EditorState.create({
        doc: value,
        extensions: [
          history(),
          keymap.of([
            { key: "Mod-b", run: (target) => run(target, (doc, from, to) => toggleWrap(doc, from, to, "**", "bold text")) },
            { key: "Mod-i", run: (target) => run(target, (doc, from, to) => toggleWrap(doc, from, to, "*", "italic text")) },
            // Tab is left to the browser, so the editor never traps keyboard focus
            ...historyKeymap,
            ...defaultKeymap,
          ]),
          markdownSupport,
          syntaxHighlighting(markdownStyle),
          macroChips,
          EditorView.lineWrapping,
          EditorView.contentAttributes.of(contentAttributes(id, ariaLabel, ariaLabelledBy)),
          EditorView.editable.of(!disabled),
          editorTheme(minRows),
          placeholder ? placeholderExtension(placeholder) : [],
          EditorView.updateListener.of((update: ViewUpdate) => {
            if (update.docChanged) onChangeRef.current(update.state.doc.toString());
          }),
        ],
      }),
    });
    view.current = editor;
    return () => {
      editor.destroy();
      view.current = null;
    };
    // Created once; value changes from outside are applied below, without losing the cursor or undo history
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const editor = view.current;
    if (!editor) return;
    const current = editor.state.doc.toString();
    if (current !== value) editor.dispatch({ changes: { from: 0, to: current.length, insert: value } });
  }, [value]);

  const command = (make: (doc: string, from: number, to: number) => Edit) => () => {
    if (view.current) run(view.current, make);
  };
  const line = (kind: LinePrefix) => command((doc, from, to) => toggleLinePrefix(doc, from, to, kind));

  return (
    <div className={disabled ? `${styles.editor} ${styles.disabled}` : styles.editor}>
      <div className={styles.toolbar} role="toolbar" aria-label="Formatting">
        <Tool label="Heading" onClick={line("heading")} disabled={disabled}>
          <Heading2 />
        </Tool>
        <Tool label="Bold (Ctrl or Cmd+B)" onClick={command((doc, from, to) => toggleWrap(doc, from, to, "**", "bold text"))} disabled={disabled}>
          <Bold />
        </Tool>
        <Tool label="Italic (Ctrl or Cmd+I)" onClick={command((doc, from, to) => toggleWrap(doc, from, to, "*", "italic text"))} disabled={disabled}>
          <Italic />
        </Tool>
        <span className={styles.separator} aria-hidden="true" />
        <Tool label="Bulleted list" onClick={line("bullet")} disabled={disabled}>
          <List />
        </Tool>
        <Tool label="Numbered list" onClick={line("number")} disabled={disabled}>
          <ListOrdered />
        </Tool>
        <Tool label="Quote" onClick={line("quote")} disabled={disabled}>
          <Quote />
        </Tool>
        <span className={styles.separator} aria-hidden="true" />
        <Tool label="Inline code" onClick={command((doc, from, to) => toggleWrap(doc, from, to, "`", "code"))} disabled={disabled}>
          <Code />
        </Tool>
        <Tool label="Link" onClick={command(insertLink)} disabled={disabled}>
          <Link2 />
        </Tool>
        <span className={styles.hint}>Markdown</span>
      </div>
      <div ref={host} className={styles.surface} />
    </div>
  );
}

function Tool({
  label,
  onClick,
  disabled,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled: boolean;
  children: ReactNode;
}) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className={styles.tool}
      aria-label={label}
      title={label}
      disabled={disabled}
      // Keep the editor's selection: a toolbar click must not move focus first
      onMouseDown={(event) => event.preventDefault()}
      onClick={onClick}
    >
      {children}
    </Button>
  );
}

/** Apply one of `markdownCommands` to the main selection, as one undoable step. */
function run(view: EditorView, make: (doc: string, from: number, to: number) => Edit): boolean {
  const { from, to } = view.state.selection.main;
  const edit = make(view.state.doc.toString(), from, to);
  view.dispatch({ changes: edit.change, selection: edit.selection, scrollIntoView: true, userEvent: "input.format" });
  view.focus();
  return true;
}

function contentAttributes(id?: string, ariaLabel?: string, ariaLabelledBy?: string): Record<string, string> {
  return {
    role: "textbox",
    "aria-multiline": "true",
    ...(id ? { id } : {}),
    ...(ariaLabel ? { "aria-label": ariaLabel } : {}),
    ...(ariaLabelledBy ? { "aria-labelledby": ariaLabelledBy } : {}),
  };
}

/**
 * GitHub-flavoured Markdown, built from the parser alone. `@codemirror/lang-markdown` also bundles HTML, CSS and
 * JavaScript parsers for code blocks and inline HTML, which instructions don't need: leaving them out cuts the
 * editor's download by about 40% (177KB to 104KB gzipped).
 */
const markdownSupport = new LanguageSupport(
  new Language(defineLanguageFacet({ commentTokens: { block: { open: "<!--", close: "-->" } } }), markdownParser.configure(GFM), [], "markdown")
);

/** `{{ lead_form:contact }}`, `{{ steps.draft.output }}`: shown as chips so they stand out and aren't mistyped. */
const macroChips: Extension = ViewPlugin.fromClass(
  class {
    decorations: DecorationSet;
    private readonly matcher = new MatchDecorator({
      regexp: /\{\{[^{}\n]*\}\}/g,
      decoration: Decoration.mark({ class: "cm-md-macro" }),
    });
    constructor(view: EditorView) {
      this.decorations = this.matcher.createDeco(view);
    }
    update(update: ViewUpdate) {
      this.decorations = this.matcher.updateDeco(update, this.decorations);
    }
  },
  { decorations: (plugin) => plugin.decorations }
);

const markdownStyle = HighlightStyle.define([
  { tag: tags.heading1, fontSize: "1.3em", fontWeight: "700", color: "var(--text-primary)" },
  { tag: tags.heading2, fontSize: "1.15em", fontWeight: "650", color: "var(--text-primary)" },
  { tag: [tags.heading3, tags.heading4, tags.heading5, tags.heading6], fontWeight: "650", color: "var(--text-primary)" },
  { tag: tags.strong, fontWeight: "700", color: "var(--text-primary)" },
  { tag: tags.emphasis, fontStyle: "italic" },
  { tag: tags.strikethrough, textDecoration: "line-through" },
  { tag: tags.link, color: "var(--gradient-start)" },
  { tag: tags.url, color: "var(--text-muted)" },
  { tag: tags.monospace, fontFamily: "var(--font-mono, ui-monospace, SFMono-Regular, Consolas, monospace)", color: "var(--json-string)" },
  { tag: tags.quote, color: "var(--text-secondary)", fontStyle: "italic" },
  // Markup characters (#, *, >, backticks) stay visible but quiet: the text is the source, never hidden
  { tag: tags.processingInstruction, color: "var(--text-muted)" },
  { tag: tags.contentSeparator, color: "var(--text-muted)" },
]);

function editorTheme(minRows: number): Extension {
  return EditorView.theme({
    "&": { backgroundColor: "transparent", color: "var(--text-secondary)", fontSize: "0.9375rem" },
    "&.cm-focused": { outline: "none" },
    ".cm-scroller": {
      fontFamily: "inherit",
      lineHeight: String(LINE_HEIGHT_REM),
      minHeight: `${minRows * LINE_HEIGHT_REM}rem`,
      maxHeight: "70vh",
      overflow: "auto",
    },
    ".cm-content": { padding: "0.75rem 1rem", caretColor: "var(--gradient-start)" },
    ".cm-line": { padding: "0" },
    ".cm-placeholder": { color: "var(--text-muted)" },
    ".cm-cursor": { borderLeftColor: "var(--gradient-start)" },
    "&.cm-focused .cm-selectionBackground, .cm-selectionBackground, ::selection": {
      backgroundColor: "rgba(var(--gradient-start-rgb), 0.28)",
    },
    ".cm-md-macro": {
      backgroundColor: "rgba(var(--gradient-start-rgb), 0.16)",
      borderRadius: "0.3rem",
      color: "var(--json-key)",
      fontFamily: "var(--font-mono, ui-monospace, SFMono-Regular, Consolas, monospace)",
      fontSize: "0.85em",
      padding: "0.05rem 0.3rem",
    },
  });
}
