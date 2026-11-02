import { iamErrorMessage } from "../../../services/iam/errors";

export interface MutationState {
  pending: boolean;
  error?: string;
  success?: string;
}

/** One IAM change at a time: report it pending, then its outcome, then reload what the page shows. */
export async function runMutation(
  inFlight: { current: boolean },
  operation: () => Promise<unknown>,
  successMessage: string,
  report: (state: MutationState) => void,
  reload: () => void,
): Promise<void> {
  if (inFlight.current) return;
  inFlight.current = true;
  report({ pending: true });
  try {
    await operation();
    report({ pending: false, success: successMessage });
  } catch (error) {
    report({ pending: false, error: iamErrorMessage(error) });
  } finally {
    inFlight.current = false;
    // A failure can still have changed something (an invitation whose email failed, a permission another admin
    // changed first), so reload either way.
    reload();
  }
}
