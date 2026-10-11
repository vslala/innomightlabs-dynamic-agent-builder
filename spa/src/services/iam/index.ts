import { httpClient } from "../http/client";

export interface IamCapabilities {
  can_list_members: boolean;
  can_invite: boolean;
}

export interface IamMember {
  user_id: string;
  email: string;
  name: string;
  status: string;
  joined_at: string;
  is_owner: boolean;
  group_ids: string[];
  policies: string[];
}

class IamService {
  async getCapabilities(signal?: AbortSignal): Promise<IamCapabilities> {
    return httpClient.get<IamCapabilities>("/iam/capabilities", { signal });
  }

  async listMembers(signal?: AbortSignal): Promise<IamMember[]> {
    return httpClient.get<IamMember[]>("/iam/members", { signal });
  }
}

export const iamService = new IamService();
