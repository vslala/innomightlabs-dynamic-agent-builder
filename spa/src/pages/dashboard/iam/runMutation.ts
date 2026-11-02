import { invitationErrorMessage } from "../../../services/iam/invitations";

export interface InvitationMutationState {
  pending: boolean;
  error?: string;
  success?: string;
}

export async function mutateInvitation(
  inFlight: { current: boolean },
  operation: () => Promise<unknown>,
  successMessage: string,
  report: (state: InvitationMutationState) => void,
  reload: () => void,
): Promise<void> {
  if (inFlight.current) return;
  inFlight.current = true;
  report({ pending: true });
  try {
    await operation();
    report({ pending: false, success: successMessage });
  } catch (error) {
    report({ pending: false, error: invitationErrorMessage(error) });
  } finally {
    inFlight.current = false;
    // Failed delivery can still persist an invitation; refresh on failure too.
    reload();
  }
}
