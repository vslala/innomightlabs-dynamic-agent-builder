import { iamService, type IamCapabilities, type IamMember } from "../../../services/iam";
import { iamErrorMessage } from "../../../services/iam/errors";
import { invitationService, type Invitation } from "../../../services/iam/invitations";

export interface MembersData {
  capabilities: IamCapabilities;
  members: IamMember[];
  invitations: Invitation[];
  directoryError?: string;
}

export async function loadMembers(signal: AbortSignal): Promise<MembersData> {
  const capabilities = await iamService.getCapabilities(signal);
  signal.throwIfAborted();
  if (!capabilities.can_list_members) return { capabilities, members: [], invitations: [] };
  const [members, invitations] = await Promise.allSettled([
    iamService.listMembers(signal), invitationService.list(signal),
  ]);
  signal.throwIfAborted();
  const errors = [members, invitations].flatMap((result) => result.status === "rejected" ? [iamErrorMessage(result.reason)] : []);
  return {
    capabilities,
    members: members.status === "fulfilled" ? members.value : [],
    invitations: invitations.status === "fulfilled" ? invitations.value : [],
    ...(errors.length ? { directoryError: errors.join(" ") } : {}),
  };
}
