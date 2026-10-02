import { forwardRef, useState, type KeyboardEvent } from "react";
import { ArrowUp } from "lucide-react";

interface ComposerProps {
  placeholder: string;
  disabled: boolean;
  onSend: (content: string) => void;
}

const MAX_ROWS = 6;

export const Composer = forwardRef<HTMLTextAreaElement, ComposerProps>(function Composer({ placeholder, disabled, onSend }, ref) {
  const [value, setValue] = useState("");
  const rows = Math.min(MAX_ROWS, Math.max(1, value.split("\n").length));

  const send = () => {
    const content = value.trim();
    if (!content || disabled) return;
    onSend(content);
    setValue("");
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      send();
    }
  };

  return (
    <div className="ie-composer">
      <textarea
        ref={ref}
        className="ie-composer-input"
        rows={rows}
        value={value}
        placeholder={placeholder}
        aria-label="Message"
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={onKeyDown}
      />
      <button type="button" className="ie-send" aria-label="Send message" disabled={disabled || !value.trim()} onClick={send}>
        <ArrowUp aria-hidden="true" />
      </button>
    </div>
  );
});
