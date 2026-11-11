/**
 * How far the agent is from ready: a progress bar, then only what's left, each with the action that does it.
 * Finished checks fold under "Show N done"; when everything is done the card is a single confirmation.
 */

import { useState } from "react";
import { Check, ChevronDown, ChevronUp, CircleAlert } from "lucide-react";

import { Button } from "../../../../components/ui";
import { OverviewCard } from "./OverviewCard";
import type { SetupAction, SetupCheck } from "./setupChecks";

export function SetupCard({
  checks,
  busy,
  onAction,
}: {
  checks: SetupCheck[];
  /** An action is under way (enabling A2A), so actions wait. */
  busy: boolean;
  onAction: (action: SetupAction) => void;
}) {
  const [showDone, setShowDone] = useState(false);
  const done = checks.filter((check) => check.done);
  const open = checks.filter((check) => !check.done);
  const complete = open.length === 0;

  return (
    <OverviewCard id="agent-setup" title="Setup">
      <div className="agent-overview-progress">
        <div className="agent-overview-progress__label">
          <span>
            <strong>
              {done.length} of {checks.length}
            </strong>{" "}
            done
          </span>
          <span>{complete ? "Ready to share" : `${open.length} left`}</span>
        </div>
        <div
          className="agent-overview-progress__bar"
          role="progressbar"
          aria-label="Setup progress"
          aria-valuemin={0}
          aria-valuemax={checks.length}
          aria-valuenow={done.length}
        >
          <span
            className={complete ? "agent-overview-progress__fill agent-overview-progress__fill--done" : "agent-overview-progress__fill"}
            style={{ width: `${(done.length / checks.length) * 100}%` }}
          />
        </div>
      </div>

      {complete ? (
        <p className="agent-overview-all-set">
          <Check aria-hidden="true" />
          Everything is set up.
        </p>
      ) : (
        <>
          <CheckList checks={open} busy={busy} onAction={onAction} />
          {done.length > 0 && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="agent-overview-disclosure"
              aria-expanded={showDone}
              onClick={() => setShowDone((value) => !value)}
            >
              {showDone ? <ChevronUp /> : <ChevronDown />}
              {showDone ? "Hide" : "Show"} {done.length} done
            </Button>
          )}
          {showDone && <CheckList checks={done} busy={busy} onAction={onAction} />}
        </>
      )}
    </OverviewCard>
  );
}

function CheckList({
  checks,
  busy,
  onAction,
}: {
  checks: SetupCheck[];
  busy: boolean;
  onAction: (action: SetupAction) => void;
}) {
  return (
    <ul className="agent-overview-checks">
      {checks.map((check) => (
        <li key={check.key} className="agent-overview-checks__item">
          <span
            className={check.done ? "agent-overview-checks__icon agent-overview-checks__icon--done" : "agent-overview-checks__icon"}
            aria-hidden="true"
          >
            {check.done ? <Check /> : <CircleAlert />}
          </span>
          <span className="agent-overview-checks__text">
            <strong>{check.label}</strong>
            <small>{check.done ? check.hint : (check.blockedBy ?? check.hint)}</small>
          </span>
          {check.done ? (
            <span className="agent-overview-checks__done">Done</span>
          ) : (
            <Button
              type="button"
              variant="link"
              size="sm"
              disabled={busy || check.blockedBy !== null}
              onClick={() => onAction(check.action)}
            >
              {check.actionLabel}
            </Button>
          )}
        </li>
      ))}
    </ul>
  );
}
