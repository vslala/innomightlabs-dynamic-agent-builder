import { invitationService } from "../../services/iam/invitations";
import { accountService } from "../../services/accounts";

import { PENDING_INVITATION_KEY } from "./continuation";

export async function acceptInvitation(token: string): Promise<void> {
  const accepted = await invitationService.accept(token);

  // Always persist the server selection too, even if this tab already chose it.
  await accountService.switchTo(accepted.account_id, { redirectOnAuthError: false });
  sessionStorage.removeItem(PENDING_INVITATION_KEY);
}
