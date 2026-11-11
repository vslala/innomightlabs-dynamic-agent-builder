/**
 * The agent's instructions: read as rendered Markdown, folded when long, and edited in place in the same card
 * with the Markdown editor, so changing one sentence doesn't mean opening the whole agent form.
 * Folding hides nothing: the whole text stays on the page.
 */

import { useState } from "react";
import { ChevronDown, ChevronUp, Pencil } from "lucide-react";

import { Button, MarkdownEditor, MarkdownRenderer } from "../../../../components/ui";
import { OverviewCard } from "./OverviewCard";

const FOLD_AFTER_CHARS = 900;

export function InstructionsCard({
  instructions,
  onSave,
}: {
  instructions: string;
  /** Saves new instructions; rejects with a message to show if it fails. */
  onSave: (instructions: string) => Promise<void>;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const editing = draft !== null;

  const save = async () => {
    if (draft === null) return;
    setSaving(true);
    setError(null);
    try {
      await onSave(draft);
      setDraft(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save the instructions. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <OverviewCard
      id="agent-instructions"
      title="Instructions"
      meta={`${wordCount(draft ?? instructions).toLocaleString()} words`}
      actions={
        editing ? null : (
          <Button type="button" variant="ghost" size="sm" onClick={() => setDraft(instructions)}>
            <Pencil />
            Edit
          </Button>
        )
      }
    >
      {editing ? (
        <>
          <MarkdownEditor
            value={draft}
            onChange={setDraft}
            ariaLabelledBy="agent-instructions-title"
            placeholder="What this agent is for, how it works, and the rules it follows"
            minRows={14}
          />
          {error ? (
            <p className="agent-overview-error" role="alert">
              {error}
            </p>
          ) : null}
          <div className="agent-overview-edit-actions">
            <Button type="button" variant="outline" onClick={() => setDraft(null)} disabled={saving}>
              Cancel
            </Button>
            <Button type="button" onClick={() => void save()} disabled={saving || draft === instructions}>
              {saving ? "Saving..." : "Save instructions"}
            </Button>
          </div>
        </>
      ) : (
        <ReadInstructions instructions={instructions} />
      )}
    </OverviewCard>
  );
}

function ReadInstructions({ instructions }: { instructions: string }) {
  const [expanded, setExpanded] = useState(false);
  if (!instructions.trim()) return <p className="agent-overview-muted">No instructions yet.</p>;
  const long = instructions.length > FOLD_AFTER_CHARS;

  return (
    <>
      <div className={long && !expanded ? "agent-overview-prose agent-overview-prose--folded" : "agent-overview-prose"}>
        <MarkdownRenderer content={instructions} />
      </div>
      {long && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="agent-overview-disclosure"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? <ChevronUp /> : <ChevronDown />}
          {expanded ? "Show less" : "Show all instructions"}
        </Button>
      )}
    </>
  );
}

function wordCount(text: string): number {
  const trimmed = text.trim();
  return trimmed ? trimmed.split(/\s+/).length : 0;
}
