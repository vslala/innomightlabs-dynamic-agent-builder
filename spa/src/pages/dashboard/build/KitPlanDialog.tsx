import { AlertTriangle, Pencil } from "lucide-react";
import {
  Alert,
  AlertDescription,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Spinner,
  StatusBadge,
} from "../../../components/ui";
import type { KitPlan } from "../../../services/kits/KitApiService";
import { changingSteps, PLAN_ACTIONS } from "./kitView";
import styles from "./KitDetailPage.module.css";

interface KitPlanDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  /** Null while it's being planned. */
  plan: KitPlan | null;
  error: string | null;
  confirmLabel: string;
  /** For removing: the confirm button is red. */
  destructive?: boolean;
  applying: boolean;
  onConfirm: () => void;
}

/** What a rollback or a removal would do, shown before anything happens. Confirming applies exactly this plan. */
export function KitPlanDialog({
  open,
  onOpenChange,
  title,
  description,
  plan,
  error,
  confirmLabel,
  destructive = false,
  applying,
  onConfirm,
}: KitPlanDialogProps) {
  const steps = plan ? changingSteps(plan) : [];
  const drift = plan ? plan.steps.flatMap((step) => step.drift.map((line) => `${step.resource}: ${line}`)) : [];

  return (
    <Dialog open={open} onOpenChange={(next) => !applying && onOpenChange(next)}>
      <DialogContent className={styles.planDialog}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        {!plan && !error && (
          <div className={styles.planLoading}>
            <Spinner size="sm" /> Working out what changes…
          </div>
        )}
        {error && (
          <Alert variant="error">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {plan && (
          <div className={styles.planBody}>
            {plan.blockers.length > 0 && (
              <Alert variant="error">
                <AlertDescription>
                  {plan.blockers.map((issue) => (
                    <p key={`${issue.path}-${issue.message}`}>
                      {issue.message}
                      {issue.hint ? ` ${issue.hint}` : ""}
                    </p>
                  ))}
                </AlertDescription>
              </Alert>
            )}

            {steps.length === 0 ? (
              <p className={styles.muted}>Nothing would change: the kit already matches.</p>
            ) : (
              <ul className={styles.planSteps}>
                {steps.map((step) => (
                  <li key={step.resource} className={styles.planStep}>
                    <StatusBadge size="sm" {...PLAN_ACTIONS[step.action]} />
                    <span>{step.summary}</span>
                  </li>
                ))}
              </ul>
            )}

            {plan.removals.length > 0 && (
              <div className={styles.removals} role="note">
                <p className={styles.removalsTitle}>
                  <AlertTriangle aria-hidden="true" /> This can't be undone
                </p>
                <ul>
                  {plan.removals.map((removal) => (
                    <li key={removal}>{removal}</li>
                  ))}
                </ul>
              </div>
            )}

            {drift.length > 0 && (
              <div className={styles.drift}>
                <p className={styles.driftTitle}>
                  <Pencil aria-hidden="true" /> Changed outside Ada, and kept
                </p>
                <ul>
                  {drift.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={applying}>
            Cancel
          </Button>
          <Button
            variant={destructive ? "destructive" : "default"}
            onClick={onConfirm}
            disabled={!plan?.ok || !plan.plan_id || applying}
          >
            {applying ? "Working…" : confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
