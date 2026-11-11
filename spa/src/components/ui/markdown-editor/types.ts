export interface MarkdownEditorProps {
  /** Given to the editable area, so a `<label htmlFor>` names it. */
  id?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  /** Height before it grows with the text (it scrolls past 70% of the viewport). */
  minRows?: number;
  disabled?: boolean;
  ariaLabel?: string;
  ariaLabelledBy?: string;
}
