import { useState } from "react";
import { ShieldCheck } from "lucide-react";

import { Button } from "../../../../components/ui";
import { ConsentBlocks } from "../../../../components/chat/consent/ConsentCard";
import type { StepConsentState } from "../../../../types/consent";

/**
 * A step that acts for the owner, shown as it will run (templates and all) for them to approve once. The automation
 * runs it on its own after that, until the step changes. The same consent Ila asks for in her chat.
 */
export function StepConsentPanel({
  consent,
  readOnly,
  onApprove,
  onRevoke,
}: {
  consent: StepConsentState;
  readOnly: boolean;
  onApprove: (grantedActions: string[]) => Promise<void>;
  onRevoke: () => Promise<void>;
}) {
  const grantsBlock = consent.blocks.find((block) => block.kind === "grants");
  const ticked = grantsBlock
    ? (consent.state === "granted" ? consent.granted_actions : grantsBlock.items.filter((item) => item.checked).map((item) => item.key))
    : [];
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const deciding = consent.state !== "granted" && !readOnly;
  const edit = deciding && grantsBlock
    ? {
        editable: new Set([grantsBlock.argument]),
        draft: { [grantsBlock.argument]: ticked, ...draft },
        onChange: (argument: string, value: unknown) => setDraft((current) => ({ ...current, [argument]: value })),
      }
    : undefined;

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      setDraft({});
    } catch (e) {
      setError(e instanceof Error ? e.message : "That didn't go through. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const heading =
    consent.state === "granted"
      ? "Approved by you"
      : consent.state === "stale"
        ? "This step changed since you approved it"
        : consent.required
          ? "Needs your approval before it can run"
          : "Choose what its agent may do on its own";

  return (
    <div className="chain-card__consent" aria-label="Approval">
      <div className="chain-card__consent-head">
        <ShieldCheck className="h-4 w-4" aria-hidden />
        <strong>{heading}</strong>
        {consent.state === "granted" && consent.granted_at && (
          <small>{new Date(consent.granted_at).toLocaleDateString()}</small>
        )}
      </div>
      <ConsentBlocks blocks={consent.blocks} edit={edit} />
      {error && <p className="chain-card__consent-error">{error}</p>}
      {!readOnly && (
        <div className="chain-card__consent-actions">
          {deciding ? (
            <Button
              size="sm"
              disabled={busy}
              onClick={() =>
                run(() => onApprove(grantsBlock ? ((edit?.draft[grantsBlock.argument] as string[]) ?? []) : []))
              }
            >
              {grantsBlock ? "Allow these" : "Approve this step"}
            </Button>
          ) : (
            <Button size="sm" variant="outline" disabled={busy} onClick={() => run(onRevoke)}>
              Revoke
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
