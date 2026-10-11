import { iamService, type IamCapabilities, type IamMember } from "../../../services/iam";

export interface MembersData {
  capabilities: IamCapabilities;
  members: IamMember[];
}

export async function loadMembers(signal: AbortSignal): Promise<MembersData> {
  const capabilities = await iamService.getCapabilities(signal);
  // Do not start a second request after this page has been left or retried.
  signal.throwIfAborted();
  const members = capabilities.can_list_members
    ? await iamService.listMembers(signal)
    : [];
  return { capabilities, members };
}
