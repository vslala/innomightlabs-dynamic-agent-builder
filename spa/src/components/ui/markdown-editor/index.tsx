/**
 * A Markdown editor with live styling (`editor-view.tsx`), loaded on first use so CodeMirror stays out of the
 * main bundle. While it loads, the same frame shows at the same height.
 *
 * If the editor can't load (a stale tab after a deploy, a dropped connection), the field falls back to a plain
 * textarea over the same value, so the person can still edit and save instead of losing the page.
 */

import { Component, lazy, Suspense, type ReactNode } from "react";

import { Textarea } from "../textarea";
import styles from "./markdown-editor.module.css";
import type { MarkdownEditorProps } from "./types";

const MarkdownEditorView = lazy(() => import("./editor-view"));

const LINE_HEIGHT_REM = 1.6;

export type { MarkdownEditorProps } from "./types";

export function MarkdownEditor(props: MarkdownEditorProps) {
  const minRows = props.minRows ?? 8;
  return (
    <PlainOnFailure fallback={<PlainEditor {...props} minRows={minRows} />}>
      <Suspense
        fallback={
          <div className={styles.editor} style={{ minHeight: `${minRows * LINE_HEIGHT_REM + 3}rem` }}>
            <span className={styles.loading}>Loading editor…</span>
          </div>
        }
      >
        <MarkdownEditorView {...props} />
      </Suspense>
    </PlainOnFailure>
  );
}

function PlainEditor({ id, value, onChange, placeholder, minRows, disabled, ariaLabel, ariaLabelledBy }: MarkdownEditorProps) {
  return (
    <Textarea
      id={id}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
      rows={minRows}
      disabled={disabled}
      aria-label={ariaLabel}
      aria-labelledby={ariaLabelledBy}
    />
  );
}

class PlainOnFailure extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    console.error("The Markdown editor couldn't load; using a plain text area instead.", error);
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
