/**
 * Whether the signed-in person may change the active account's settings and credentials: its providers,
 * connectors, Agent2Agent, Dream and smart-suggestion settings. They belong to the account; its admins
 * manage them and every member's agents use them.
 */

import { httpClient } from "../http/client";

export interface SettingsAccess {
  can_manage: boolean;
}

class SettingsAccessService {
  async get(): Promise<SettingsAccess> {
    return httpClient.get<SettingsAccess>("/settings/access");
  }
}

export const settingsAccessService = new SettingsAccessService();
