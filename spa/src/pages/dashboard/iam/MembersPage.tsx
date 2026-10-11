import * as React from "react";
import { invitationService, invitationErrorMessage } from "../../../services/iam/invitations";
import { MembersPanel, type MembersState } from "./MembersPanel";
import { loadMembers } from "./loadMembers";
import { mutateInvitation, type InvitationMutationState } from "./mutateInvitation";

export function MembersPage() {
  const [state, setState] = React.useState<MembersState>({ status: "loading" });
  const [attempt, setAttempt] = React.useState(0);
  const [mutation, setMutation] = React.useState<InvitationMutationState>({ pending: false });
  const inFlight = React.useRef(false);
  const mounted = React.useRef(false);

  React.useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  React.useEffect(() => {
    const controller = new AbortController();
    loadMembers(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) setState({ status: "loaded", ...data });
      },
      (error: unknown) => {
        if (!controller.signal.aborted) setState({ status: "error", message: invitationErrorMessage(error) });
      },
    );
    return () => controller.abort();
  }, [attempt]);

  async function mutate(operation: () => Promise<unknown>, message: string) {
    if (state.status !== "loaded" || !state.capabilities.can_invite) return;
    await mutateInvitation(inFlight, operation, message,
      (result) => { if (mounted.current) setMutation(result); },
      () => { if (mounted.current) setAttempt((value) => value + 1); },
    );
  }

  return <MembersPanel state={state} onRetry={() => setAttempt((value) => value + 1)} actions={{
    ...mutation,
    onInvite: (email) => { if (email) void mutate(() => invitationService.create(email), "Invitation sent."); },
    onResend: (id) => { void mutate(() => invitationService.resend(id), "Invitation resent."); },
    onRevoke: (id) => { void mutate(() => invitationService.revoke(id), "Invitation revoked."); },
  }} />;
}
