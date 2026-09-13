import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Check,
  ChevronLeft,
  Loader2,
  MoreHorizontal,
  Play,
  Share2,
  Trash2,
} from "lucide-react";
import { Link } from "react-router-dom";

import {
  Button,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../../../components/ui";
import type { AutomationResponse, AutomationStatus } from "../../../../types/automation";
import type { SaveState } from "../hooks/useAutomationDraft";

/**
 * The workspace header: identity, save state, status, and the run control.
 *
 * There is no save button. Edits persist on their own, so the only thing the
 * user needs is an honest indicator of where the save got to.
 */
export function WorkspaceTopBar({
  automation,
  saveState,
  saveError,
  errorCount,
  onRetrySave,
  onRename,
  onStatusChange,
  onTest,
  onPublish,
  onDelete,
  onShowIssues,
  busy,
}: {
  automation: AutomationResponse;
  saveState: SaveState;
  saveError: string | null;
  errorCount: number;
  onRetrySave: () => void;
  onRename: (title: string) => void;
  onStatusChange: (status: AutomationStatus) => void;
  onTest: () => void;
  onPublish: () => void;
  onDelete: () => void;
  onShowIssues: () => void;
  busy: boolean;
}) {
  // `null` means "not editing", so a rename elsewhere is always reflected
  // without an effect syncing props into state.
  const [draftTitle, setDraftTitle] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const editingTitle = draftTitle !== null;
  const title = draftTitle ?? automation.title;

  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) setMenuOpen(false);
    };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, [menuOpen]);

  const commitTitle = () => {
    const next = (draftTitle ?? "").trim();
    setDraftTitle(null);
    if (next && next !== automation.title) onRename(next);
  };

  return (
    <header className="automation-workspace__topbar">
      <div className="automation-workspace__identity">
        <Button variant="ghost" size="icon" asChild>
          <Link to="/dashboard/automations" aria-label="Back to automations">
            <ChevronLeft className="h-5 w-5" />
          </Link>
        </Button>
        {editingTitle ? (
          <Input
            autoFocus
            value={title}
            onChange={(event) => setDraftTitle(event.target.value)}
            onBlur={commitTitle}
            onKeyDown={(event) => {
              if (event.key === "Enter") commitTitle();
              if (event.key === "Escape") setDraftTitle(null);
            }}
            className="automation-workspace__title-input"
          />
        ) : (
          <Button
            variant="ghost"
            className="automation-workspace__title"
            onClick={() => setDraftTitle(automation.title)}
            title="Rename automation"
          >
            {automation.title}
          </Button>
        )}
        <SaveIndicator state={saveState} error={saveError} onRetry={onRetrySave} />
      </div>

      <div className="automation-workspace__actions">
        {errorCount > 0 && (
          <Button variant="ghost" size="sm" onClick={onShowIssues} className="automation-workspace__issues">
            <AlertTriangle className="h-4 w-4" />
            {errorCount} {errorCount === 1 ? "issue" : "issues"}
          </Button>
        )}

        <Select
          value={automation.status}
          onValueChange={(value) => onStatusChange(value as AutomationStatus)}
          disabled={busy}
        >
          <SelectTrigger className="automation-workspace__status-trigger">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="draft">Draft</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="disabled">Disabled</SelectItem>
          </SelectContent>
        </Select>

        <Button size="sm" onClick={onTest} disabled={busy}>
          <Play className="h-4 w-4" />
          Test
        </Button>

        <div className="automation-workspace__menu" ref={menuRef}>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setMenuOpen((open) => !open)}
            aria-label="More actions"
          >
            <MoreHorizontal className="h-4 w-4" />
          </Button>
          {menuOpen && (
            <div className="automation-workspace__menu-items" role="menu">
              <Button
                variant="ghost"
                className="automation-workspace__menu-item"
                onClick={() => {
                  setMenuOpen(false);
                  onPublish();
                }}
              >
                <Share2 className="h-4 w-4" />
                Publish to marketplace
              </Button>
              <Button
                variant="ghost"
                className="automation-workspace__menu-item automation-workspace__menu-item--danger"
                onClick={() => {
                  setMenuOpen(false);
                  onDelete();
                }}
              >
                <Trash2 className="h-4 w-4" />
                Delete automation
              </Button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

function SaveIndicator({
  state,
  error,
  onRetry,
}: {
  state: SaveState;
  error: string | null;
  onRetry: () => void;
}) {
  if (state === "saving") {
    return (
      <span className="automation-workspace__save automation-workspace__save--busy">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Saving…
      </span>
    );
  }
  if (state === "error") {
    return (
      <Button
        variant="ghost"
        size="sm"
        className="automation-workspace__save automation-workspace__save--error"
        onClick={onRetry}
        title={error ?? "Retry save"}
      >
        <AlertTriangle className="h-3.5 w-3.5" />
        Save failed — retry
      </Button>
    );
  }
  return (
    <span className="automation-workspace__save">
      <Check className="h-3.5 w-3.5" />
      Saved
    </span>
  );
}
